# -*- coding: utf-8 -*-
"""
Cache TTL em memoria para respostas Flask.

Projeto: Portal Operacoes RNO
Uso inicial: dash_quebra_rno

Caracteristicas:
- TTL configuravel;
- limite de entradas com descarte das mais antigas;
- bloqueio por chave para evitar consultas duplicadas concorrentes;
- copia segura do corpo, status e headers da resposta;
- estatisticas de hit, miss, wait, expiracao e descarte;
- invalidacao total ou por prefixo;
- sem dependencias externas.

Observacao:
O cache e local ao processo Python. Em producao com varios workers,
cada worker possui seu proprio cache. Para o ambiente Flask/Laragon
atual, esse comportamento e adequado.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Hashable

from flask import Response, jsonify, make_response, request


@dataclass
class CacheEntry:
    created_at: float
    expires_at: float
    status_code: int
    headers: list[tuple[str, str]]
    body: bytes
    content_type: str | None


class TTLResponseCache:
    """Cache thread-safe de respostas HTTP Flask."""

    def __init__(self, ttl_seconds: int = 600, max_entries: int = 128,
                 name: str = "response-cache") -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds deve ser maior que zero")
        if max_entries <= 0:
            raise ValueError("max_entries deve ser maior que zero")

        self.ttl_seconds = int(ttl_seconds)
        self.max_entries = int(max_entries)
        self.name = str(name)

        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "waits": 0,
            "expired": 0,
            "evictions": 0,
            "stores": 0,
            "errors_not_cached": 0,
            "invalidations": 0,
        }

    @staticmethod
    def _now() -> float:
        return time.monotonic()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def _remove_expired_locked(self, now: float) -> None:
        expired_keys = [
            key for key, entry in self._entries.items()
            if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)
            self._locks.pop(key, None)
            self._stats["expired"] += 1

    def get(self, key: str) -> CacheEntry | None:
        now = self._now()
        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                self._locks.pop(key, None)
                self._stats["expired"] += 1
                return None
            self._entries.move_to_end(key)
            return copy.copy(entry)

    def put(self, key: str, response: Response) -> None:
        now = self._now()
        headers = [
            (k, v) for k, v in response.headers.items()
            if k.lower() not in {
                "content-length", "date", "server", "connection",
                "x-cache", "x-cache-age-ms", "x-cache-key"
            }
        ]
        entry = CacheEntry(
            created_at=now,
            expires_at=now + self.ttl_seconds,
            status_code=int(response.status_code),
            headers=headers,
            body=bytes(response.get_data()),
            content_type=response.content_type,
        )

        with self._guard:
            self._remove_expired_locked(now)
            self._entries[key] = entry
            self._entries.move_to_end(key)
            self._stats["stores"] += 1

            while len(self._entries) > self.max_entries:
                old_key, _ = self._entries.popitem(last=False)
                self._locks.pop(old_key, None)
                self._stats["evictions"] += 1

    def response_from_entry(self, entry: CacheEntry, key: str,
                            cache_state: str = "HIT") -> Response:
        response = Response(
            response=entry.body,
            status=entry.status_code,
            content_type=entry.content_type,
        )
        for header, value in entry.headers:
            response.headers[header] = value
        age_ms = max(0.0, (self._now() - entry.created_at) * 1000.0)
        response.headers["X-Cache"] = cache_state
        response.headers["X-Cache-Age-Ms"] = f"{age_ms:.2f}"
        response.headers["X-Cache-Key"] = key[:16]
        return response

    def invalidate(self, prefix: str | None = None) -> int:
        with self._guard:
            if prefix is None:
                qtd = len(self._entries)
                self._entries.clear()
                self._locks.clear()
            else:
                keys = [k for k in self._entries if k.startswith(prefix)]
                qtd = len(keys)
                for key in keys:
                    self._entries.pop(key, None)
                    self._locks.pop(key, None)
            self._stats["invalidations"] += 1
            return qtd

    def stats(self) -> dict[str, Any]:
        now = self._now()
        with self._guard:
            self._remove_expired_locked(now)
            data = dict(self._stats)
            data.update({
                "name": self.name,
                "entries": len(self._entries),
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries,
                "keys": [k[:16] for k in self._entries.keys()],
            })
            total = data["hits"] + data["misses"]
            data["hit_rate_pct"] = round(
                data["hits"] / total * 100.0, 2
            ) if total else 0.0
            return data

    def record_hit(self) -> None:
        with self._guard:
            self._stats["hits"] += 1

    def record_miss(self) -> None:
        with self._guard:
            self._stats["misses"] += 1

    def record_wait(self) -> None:
        with self._guard:
            self._stats["waits"] += 1

    def record_error_not_cached(self) -> None:
        with self._guard:
            self._stats["errors_not_cached"] += 1

    def cached(self, key_builder: Callable[[], str] | None = None,
               cache_success_only: bool = True) -> Callable:
        """Decorator para cachear uma view Flask."""

        def decorator(view_func: Callable) -> Callable:
            @wraps(view_func)
            def wrapped(*args, **kwargs):
                raw_key = key_builder() if key_builder else request.full_path
                key = str(raw_key)

                entry = self.get(key)
                if entry is not None:
                    self.record_hit()
                    return self.response_from_entry(entry, key, "HIT")

                self.record_miss()
                key_lock = self._lock_for(key)

                acquired_immediately = key_lock.acquire(blocking=False)
                if not acquired_immediately:
                    self.record_wait()
                    key_lock.acquire()
                    entry = self.get(key)
                    if entry is not None:
                        self.record_hit()
                        key_lock.release()
                        return self.response_from_entry(entry, key, "HIT-AFTER-WAIT")

                try:
                    # Double-check apos obter o lock.
                    entry = self.get(key)
                    if entry is not None:
                        self.record_hit()
                        return self.response_from_entry(entry, key, "HIT-AFTER-LOCK")

                    result = view_func(*args, **kwargs)
                    response = make_response(result)
                    response.headers["X-Cache"] = "MISS"
                    response.headers["X-Cache-Key"] = key[:16]

                    pode_cachear = (
                        not cache_success_only
                        or 200 <= response.status_code < 300
                    )
                    if pode_cachear:
                        self.put(key, response)
                    else:
                        self.record_error_not_cached()
                    return response
                finally:
                    key_lock.release()

            return wrapped
        return decorator


def canonical_request_key(prefix: str,
                          ignored_args: set[str] | None = None) -> str:
    """
    Cria chave deterministica usando rota e querystring ordenada.

    Valores repetidos sao ordenados. Parametros em ignored_args nao
    entram na chave. O modo visual pode ser ignorado quando o backend
    retornar todos os valores-base; na versao atual, mode deve continuar
    na chave para preservar a resposta correta.
    """
    ignored = ignored_args or set()
    items: list[tuple[str, tuple[str, ...]]] = []
    for name in sorted(request.args.keys()):
        if name in ignored:
            continue
        values = tuple(sorted(str(v) for v in request.args.getlist(name)))
        items.append((name, values))

    payload = json.dumps(
        {"path": request.path, "args": items},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"
