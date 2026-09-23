from flask import Flask

from config import config_map
from backend.extensions import db


def create_app(env: str = "dev") -> Flask:
    """Создаёт и настраивает экземпляр Flask.

    :param env: имя окружения ("dev" | "prod" | "test")
    """
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(config_map[env])

    db.init_app(app)
    _register_blueprints(app)
    _register_error_handlers(app)

    with app.app_context():
        db.create_all()

    return app


def _register_blueprints(app: Flask) -> None:
    """Регистрирует все blueprint'ы приложения."""
    from backend.blueprints.main import bp as main_bp
    from backend.blueprints.procurement import bp as procurement_bp
    from backend.blueprints.suppliers import bp as suppliers_bp
    from backend.blueprints.analytics import bp as analytics_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(procurement_bp, url_prefix="/api/v1/procurement")
    app.register_blueprint(suppliers_bp,   url_prefix="/api/v1/suppliers")
    app.register_blueprint(analytics_bp,   url_prefix="/api/v1/analytics")

def _register_error_handlers(app: Flask) -> None:
    """Единый JSON-формат ошибок для API."""
    from backend.utils.errors import json_error

    @app.errorhandler(404)
    def _404(_):
        return json_error("not_found", "Ресурс не найден", 404)

    @app.errorhandler(500)
    def _500(_):
        return json_error("internal_error", "Внутренняя ошибка сервера", 500)


if __name__ == "__main__":
    create_app().run(port=5000)