# -*- coding: utf-8 -*-
"""Normalização auditável das fontes individuais de parceira TOA."""
from __future__ import annotations
import re
import unicodedata
import pandas as pd

# Somente equivalências confirmadas ou grafias inequívocas.
DE_PARA_TOA_PARCEIRA = {
    "HUSERVICOS": "HU SERVIÇOS",
    "HU SERVICOS": "HU SERVIÇOS",
    "H U SERVICOS": "HU SERVIÇOS",
    "AFLINE": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "AFLINE INSTALACAO E MANUT ELETRICA": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "AFLINE INSTALACAO E MANUTENCAO ELET": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "AFLINE INSTALACAO E MANUTENCAO ELETRICA": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "VIA REPRESENTACOES": "VIA REPRESENTAÇÕES",
    "FUKUSHIMA SERV DE TELEC E SOLUCOES": "FUKUSHIMA SERV. DE TELEC. E SOLUÇÕES",
    "ADUARTE ALBUQUERQUE ME": "ADUARTE ALBUQUERQUE ME",
    "NAO INFORMADO": "NÃO INFORMADO",
    "NAO INFORMADA": "NÃO INFORMADO",
    "SEM INFORMACAO": "NÃO INFORMADO",
}

# DE-PARA de tokens presentes em TOA_AREA, por exemplo MAN-HUSERVICOS_ADM.
DE_PARA_TOA_AREA_TOKEN = {
    "HUSERVICOS": "HU SERVIÇOS",
    "HU": "HU SERVIÇOS",
    "AFLINE": "AFLINE INSTALAÇÃO E MANUTENÇÃO ELÉTRICA",
    "VIA": "VIA REPRESENTAÇÕES",
    "FUKUSHIMA": "FUKUSHIMA SERV. DE TELEC. E SOLUÇÕES",
    "ADUARTE": "ADUARTE ALBUQUERQUE ME",
}

INVALIDOS = {"", "NAN", "NONE", "<NA>", "NI", "NAO INFORMADO", "NAO INFORMADA"}


def chave(valor):
    texto=" ".join(str(valor or "").strip().split())
    texto=unicodedata.normalize("NFKD",texto)
    texto="".join(c for c in texto if not unicodedata.combining(c))
    return texto.upper()


def normalizar_toa_parceira(valor):
    original=" ".join(str(valor or "").strip().split())
    k=chave(original)
    if k in INVALIDOS:
        return pd.NA
    return DE_PARA_TOA_PARCEIRA.get(k, original)


def normalizar_toa_area(valor):
    original=" ".join(str(valor or "").strip().split())
    k=chave(original)
    if k in INVALIDOS:
        return pd.NA
    # Quebra por hífen, underscore, barra e espaços; escolhe apenas token conhecido.
    tokens=[t for t in re.split(r"[-_/\\\s]+",k) if t]
    for token in tokens:
        if token in DE_PARA_TOA_AREA_TOKEN:
            return DE_PARA_TOA_AREA_TOKEN[token]
    # Também aceita token conhecido contido em códigos compostos.
    for token,nome in DE_PARA_TOA_AREA_TOKEN.items():
        if token in k:
            return nome
    return pd.NA


def resolve_toa_partner_series(df):
    """Retorna (serie_parceira, metadados), sem usar EPO."""
    result=pd.Series(pd.NA,index=df.index,dtype="string")
    source=pd.Series(pd.NA,index=df.index,dtype="string")
    for col in ["PARCEIRA_NOME","TOA_PARCEIRA"]:
        if col in df.columns:
            cand=df[col].map(normalizar_toa_parceira).astype("string")
            mask=result.isna() & cand.notna() & cand.str.strip().ne("")
            result.loc[mask]=cand.loc[mask]
            source.loc[mask]=col
    if "TOA_AREA" in df.columns:
        cand=df["TOA_AREA"].map(normalizar_toa_area).astype("string")
        mask=result.isna() & cand.notna() & cand.str.strip().ne("")
        result.loc[mask]=cand.loc[mask]
        source.loc[mask]="TOA_AREA"
    meta={
        "resolved":int(result.notna().sum()),
        "unresolved":int(result.isna().sum()),
        "by_source":{str(k):int(v) for k,v in source.value_counts(dropna=True).to_dict().items()},
        "uses_epo":False,
    }
    return result,meta
