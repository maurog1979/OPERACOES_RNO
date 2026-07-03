# -*- coding: utf-8 -*-
"""
Pacote: areas.adm.desconexao
Expoe blueprints dos dashboards da area Desconexao.
"""
from .dash_executivo import bp as dash_executivo_bp
from .dash_log import bp as dash_log_bp
from .dash_parceiras import bp as dash_parceiras_bp
from .dash_backlog import bp as dash_backlog_bp
from .dash_quebra import bp_quebra

__all__ = [
    "dash_executivo_bp",
    "dash_log_bp",
    "dash_parceiras_bp",
    "dash_backlog_bp",
    "bp_quebra",
]
