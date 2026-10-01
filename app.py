import os

from flask import Flask, jsonify, redirect, request, url_for

from config import config_map
from backend.extensions import db


def create_app(env: str = "dev") -> Flask:
    """Создаёт и настраивает экземпляр Flask."""
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(config_map[env])

    db.init_app(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_template_context(app)
    _register_access_guard(app)
    _register_stateful_cache_policy(app)

    with app.app_context():
        # Для hackathon MVP используем create_all: новые таблицы auth/registry-sync
        # создаются автоматически без отдельной миграции.
        db.create_all()

    return app


def _register_blueprints(app: Flask) -> None:
    # API
    from backend.blueprints.procurement import bp as procurement_bp
    from backend.blueprints.suppliers import bp as suppliers_api_bp
    from backend.blueprints.analytics import bp as analytics_bp
    from backend.blueprints.ai import bp as ai_bp

    app.register_blueprint(procurement_bp, url_prefix="/api/v1/procurement")
    app.register_blueprint(suppliers_api_bp, url_prefix="/api/v1/suppliers")
    app.register_blueprint(analytics_bp, url_prefix="/api/v1/analytics")
    app.register_blueprint(ai_bp, url_prefix="/api/v1/ai")

    # HTML
    from backend.blueprints.main import bp as main_bp
    from backend.blueprints.dashboard import bp as dashboard_bp
    from backend.blueprints.security import bp as security_bp
    from backend.blueprints.contracts import bp as contracts_bp
    from backend.blueprints.auth import bp as auth_bp
    from backend.blueprints.admin import bp as admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(contracts_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)


def _register_template_context(app: Flask) -> None:
    from backend.services.auth import current_user

    @app.context_processor
    def _auth_context():
        return {"current_user": current_user()}



def _register_access_guard(app: Flask) -> None:
    """Закрывает весь рабочий контур от неавторизованных пользователей.

    Публичными остаются только вход, регистрация, выход и статические файлы.
    Для API возвращаем 401 JSON, для HTML перенаправляем на страницу входа.
    """
    from backend.services.auth import current_user

    public_endpoints = {
        "auth.login",
        "auth.register",
        "auth.logout",
        "main.index",
        "static",
    }

    @app.before_request
    def _auth_wall():
        endpoint = request.endpoint or ""
        if endpoint in public_endpoints or endpoint.startswith("static"):
            return None

        user = current_user()
        if user and user.is_active:
            return None

        if request.path.startswith("/api/") or request.path.startswith("/admin/api/"):
            return jsonify({
                "error": {
                    "code": "auth_required",
                    "message": "Необходимо войти в аккаунт",
                }
            }), 401

        next_url = request.full_path.rstrip("?")
        return redirect(url_for("auth.login", next=next_url))


def _register_stateful_cache_policy(app: Flask) -> None:
    """Не даёт браузеру восстановить устаревшую карту выбора из cache/back-forward cache.

    После выбора исполнителя состояние заявки меняется безвозвратно. Поэтому страницы
    рабочего жизненного цикла всегда перепроверяются на сервере.
    """

    @app.after_request
    def _no_store_stateful_pages(response):
        if request.path.startswith(("/dashboard/", "/contracts/")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

def _register_error_handlers(app: Flask) -> None:
    from backend.utils.errors import json_error

    @app.errorhandler(404)
    def _404(_):
        return json_error("not_found", "Ресурс не найден", 404)

    @app.errorhandler(500)
    def _500(_):
        return json_error("internal_error", "Внутренняя ошибка сервера", 500)


if __name__ == "__main__":
    create_app().run(
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "5000")),
    )
