# -*- coding: utf-8 -*-
"""
=====================================================================
Flask app factory do Portal Operacoes RNO
=====================================================================
ARQUIVO COMPLETO - substitua o anterior inteiro.

O QUE MUDOU
  Acrescentado o registro do blueprint dash_safra_painel, que consome
  o Data Mart desconexao_rno.

  O bloco foi colocado DENTRO de create_app(), junto aos demais
  registros. Na tentativa anterior ele ficou no nivel do modulo,
  logo apos os imports, o que gerou:
      IndentationError: unexpected indent

COEXISTENCIA
  Nenhum blueprint existente foi alterado.
  O dash_safra_v8 continua em /dash/safra/
  O novo painel responde em /dash/safra-painel/
=====================================================================
"""

from flask import Flask, render_template, abort, redirect, url_for
from config import Config
from data.areas import AREAS, get_area, get_setor
from areas.adm.desconexao.dash_safra_v8 import bp as dash_safra_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # =========================================================
    # BLUEPRINTS - SETOR DESCONEXAO (ADM)
    # =========================================================

    try:
        from areas.adm.desconexao import dash_executivo_bp
        app.register_blueprint(dash_executivo_bp)
        print("[APP] Blueprint dash_executivo registrado em /dash/executivo/")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar dash_executivo_bp: {e}")

    try:
        from areas.adm.desconexao import dash_log_bp
        app.register_blueprint(dash_log_bp)
        print("[APP] Blueprint dash_log registrado em /dash/log/")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar dash_log_bp: {e}")

    try:
        from areas.adm.desconexao import dash_parceiras_bp
        app.register_blueprint(dash_parceiras_bp)
        print("[APP] Blueprint dash_parceiras registrado em /dash/parceiras/")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar dash_parceiras_bp: {e}")

    try:
        from areas.adm.desconexao import dash_backlog_bp
        app.register_blueprint(dash_backlog_bp)
        print("[APP] Blueprint dash_backlog registrado em /dash/backlog/")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar dash_backlog_bp: {e}")

    try:
        from areas.adm.desconexao import bp_quebra
        app.register_blueprint(bp_quebra)
        print("[APP] Blueprint dash_quebra registrado em /dash/quebra/")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar bp_quebra: {e}")

    # ----- NOVO: Painel Safra sobre o Data Mart desconexao_rno -----
    try:
        from areas.adm.desconexao.dash_safra_painel import bp as dash_safra_painel_bp
        app.register_blueprint(dash_safra_painel_bp)
        print("[APP] Blueprint dash_safra_painel registrado em /dash/safra-painel/")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar dash_safra_painel_bp: {e}")

    # ----- dash_backlog_rno (Data Mart desconexao_rno) -----
    try:
        from areas.adm.desconexao.dash_backlog_rno import bp as dash_backlog_rno_bp
        app.register_blueprint(dash_backlog_rno_bp)
        print("[APP] Blueprint dash_backlog_rno registrado em /dash/backlog-rno/")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar dash_backlog_rno_bp: {e}")

    # =========================================================
    # BLUEPRINTS - ROUTES
    # =========================================================

    try:
        from routes.dash_retirada import dash_retirada_bp
        app.register_blueprint(dash_retirada_bp)
        print("[APP] Blueprint dash_retirada registrado em /dash/retirada/")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar dash_retirada_bp: {e}")

    try:
        from routes.compat_redirects import compat_redirects_bp
        app.register_blueprint(compat_redirects_bp)
        print("[APP] Blueprint compat_redirects registrado")
    except Exception as e:
        print(f"[APP] AVISO: nao foi possivel registrar compat_redirects_bp: {e}")

    # =========================================================
    # CONTEXT PROCESSOR
    # =========================================================

    @app.context_processor
    def inject_globals():
        return {
            "APP_NAME":      app.config["APP_NAME"],
            "APP_VERSION":   app.config["APP_VERSION"],
            "USER_NAME":     app.config["USER_NAME"],
            "USER_INITIALS": app.config["USER_INITIALS"],
        }

    # =========================================================
    # ROTA 1 - HOME
    # =========================================================

    @app.route("/")
    def home():
        return render_template("home.html", areas=AREAS)

    # =========================================================
    # ROTA 2 - AREA (escolha de setor)
    # =========================================================

    @app.route("/area/<area_slug>")
    def area_view(area_slug):
        area = get_area(area_slug)
        if area is None:
            abort(404)
        if area.get("ativo") and area.get("setores"):
            return render_template("area.html", area=area)
        return render_template("construcao.html", area_nome=area["nome"])

    # =========================================================
    # ROTA 3 - SETOR (generica)
    # =========================================================

    @app.route("/area/<area_slug>/<setor_slug>")
    def setor_view(area_slug, setor_slug):
        area = get_area(area_slug)
        if area is None:
            abort(404)
        setor = get_setor(area, setor_slug)
        if setor is None:
            abort(404)
        # ADM/Desconexao tem hub especifico
        if area_slug == "adm" and setor_slug == "desconexao":
            return redirect(url_for("hub_desconexao"))
        if not setor.get("ativo"):
            return render_template(
                "construcao.html",
                area_nome=f"{area['nome']} - {setor['nome']}",
            )
        return render_template(
            "construcao.html",
            area_nome=f"{area['nome']} - {setor['nome']}",
            mensagem_custom="Setor ativo em construcao.",
        )

    # =========================================================
    # HUB DESCONEXAO
    # =========================================================

    @app.route("/area/adm/desconexao/")
    def hub_desconexao():
        return render_template("hub_desconexao.html")

    @app.route("/area/<area_slug>/em-construcao")
    def em_construcao(area_slug):
        area = get_area(area_slug)
        nome = area["nome"] if area else area_slug.upper()
        return render_template("construcao.html", area_nome=nome)

    @app.errorhandler(404)
    def not_found(e):
        return render_template(
            "construcao.html",
            area_nome="Pagina nao encontrada",
        ), 404

    # =========================================================
    # PRE-CARREGAMENTO DE DADOS NO STARTUP (N2)
    # Aplica-se apenas ao banco legado.
    # O desconexao_rno usa cache sob demanda no db_desconexao.py
    # =========================================================

    try:
        from data.db import preload_tables
        preload_tables(["safra_enriquecida"])
    except Exception as e:
        print(f"[APP] AVISO: pre-carregamento falhou: {e}")

    # =========================================================
    # BLUEPRINT LEGADO - dash_safra_v8
    # Mantido em /dash/safra/ para nao quebrar o que ja funciona
    # =========================================================

    app.register_blueprint(dash_safra_bp)



    return app
