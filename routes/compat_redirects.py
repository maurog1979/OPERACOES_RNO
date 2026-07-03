# -*- coding: utf-8 -*-
from flask import Blueprint, redirect

compat_redirects_bp = Blueprint('compat_redirects', __name__)

@compat_redirects_bp.route('/area/area/area/adm/desconexao//')
@compat_redirects_bp.route('/area/area/area/adm/desconexao//')
@compat_redirects_bp.route('/area/area/adm/desconexao//')
@compat_redirects_bp.route('/area/adm/desconexao/')
def redirect_desconexao_aliases():
    return redirect('/area/area/area/adm/desconexao//', code=302)
