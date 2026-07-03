"""Setor Desconexão da área ADM."""
from .dash_executivo import bp as dash_executivo_bp

__all__ = ["dash_executivo_bp", "dash_parceiras_bp"]
from .dash_log import bp as dash_log_bp
from .dash_parceiras import bp as dash_parceiras_bp