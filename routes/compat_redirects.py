# -*- coding: utf-8 -*-
"""
Redireciona aliases antigos (acumulados de consertos anteriores) para a
rota canônica do Hub de Desconexão: /area/adm/desconexao/.
A rota canônica pertence ao hub_desconexao (definido em app.py); aqui só
mantemos os aliases legados, que não colidem.
"""
from flask import Blueprint, redirect

compat_redirects_bp = Blueprint('compat_redirects', __name__)

_CANONICA = '/area/adm/desconexao/'


@compat_redirects_bp.route('/area/area/adm/desconexao//')
@compat_redirects_bp.route('/area/area/area/adm/desconexao//')
def redirect_desconexao_aliases():
    return redirect(_CANONICA, code=302)