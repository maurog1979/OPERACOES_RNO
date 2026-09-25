"""Flask app factory do Portal Operações RNO."""
from flask import Flask, render_template, abort, redirect, url_for, jsonify, request
from config import Config
from data.areas import AREAS, get_area, get_setor
from areas.adm.desconexao.dash_safra_v8 import bp as dash_safra_bp

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    from data.db import DatabaseUnavailable

    @app.errorhandler(DatabaseUnavailable)
    def database_unavailable(error):
        app.logger.error("Falha de acesso aos dados", exc_info=True)
        return jsonify(ok=False, error="Dados temporariamente indisponíveis.",
                       message="Dados temporariamente indisponíveis."), 503

    @app.before_request
    def protect_diagnostics():
        if request.path.endswith("/api/debug") and not app.config["ENABLE_DIAGNOSTICS"]:
            abort(404)

    # Registrar Blueprints do setor Desconexão (ADM)
    from areas.adm.desconexao import dash_executivo_bp
    app.register_blueprint(dash_executivo_bp)
    print("[APP] Blueprint dash_executivo registrado em /dash/executivo/")

    from areas.adm.desconexao import dash_log_bp
    app.register_blueprint(dash_log_bp)
    print("[APP] Blueprint dash_log registrado em /dash/log/")

    from areas.adm.desconexao import dash_parceiras_bp
    app.register_blueprint(dash_parceiras_bp)
    print("[APP] Blueprint dash_parceiras registrado em /dash/parceiras/")

    @app.context_processor
    def inject_globals():
        return {
            "APP_NAME": app.config["APP_NAME"],
            "APP_VERSION": app.config["APP_VERSION"],
            "USER_NAME": app.config["USER_NAME"],
            "USER_INITIALS": app.config["USER_INITIALS"],
        }

    # =========================================================
    # ROTA 1: HOME
    # =========================================================
    @app.route("/")
    def home():
        return render_template("home.html", areas=AREAS)

    # =========================================================
    # ROTA 2: ÁREA (escolha de setor)
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
    # ROTA 3: SETOR (genérica)
    # =========================================================
    @app.route("/area/<area_slug>/<setor_slug>")
    def setor_view(area_slug, setor_slug):
        area = get_area(area_slug)
        if area is None:
            abort(404)
        setor = get_setor(area, setor_slug)
        if setor is None:
            abort(404)
        # ADM/Desconexão tem hub específico
        if area_slug == "adm" and setor_slug == "desconexao":
            return redirect(url_for("hub_desconexao"))
        if not setor.get("ativo"):
            return render_template(
                "construcao.html",
                area_nome=f"{area['nome']} · {setor['nome']}",
            )
        return render_template(
            "construcao.html",
            area_nome=f"{area['nome']} · {setor['nome']}",
            mensagem_custom="Setor ativo em construção.",
        )

    # =========================================================
    # HUB DESCONEXÃO (6 dashboards)
    # =========================================================
    @app.route("/area/adm/desconexao/")
    def hub_desconexao():
        return render_template("hub_desconexao.html")

    @app.route("/area/<area_slug>/em-construcao")
    def em_construcao(area_slug):
        area = get_area(area_slug)
        if area is None:
            abort(404)
        nome = area["nome"]
        return render_template("construcao.html", area_nome=nome)

    @app.errorhandler(404)
    def not_found(e):
        return render_template("construcao.html", area_nome="Página não encontrada",
                               mensagem_custom="O endereço informado não existe."), 404

    # ----- dash_backlog (FASE 2B - 3/4) -----

    from areas.adm.desconexao import dash_backlog_bp

    app.register_blueprint(dash_backlog_bp)

    print("[APP] Blueprint dash_backlog registrado em /dash/backlog/")

    # ----- dash_quebra (FASE 2B - 4/4) -----
    from areas.adm.desconexao import bp_quebra
    app.register_blueprint(bp_quebra)
    print("[APP] Blueprint dash_quebra registrado em /dash/quebra/")

    # ===== Pre-carregamento de dados no startup (N2) =====

    from data.db import preload_tables

    if app.config["PRELOAD_DATA"] and not app.testing:
        preload_tables(["safra_enriquecida"])

    from routes.dash_retirada import dash_retirada_bp
    app.register_blueprint(dash_retirada_bp)
    print("[APP] Blueprint dash_retirada registrado em /dash/retirada/")

    from routes.compat_redirects import compat_redirects_bp
    app.register_blueprint(compat_redirects_bp)
    print("[APP] Blueprint compat_redirects registrado")

    app.register_blueprint(dash_safra_bp)
    return app

