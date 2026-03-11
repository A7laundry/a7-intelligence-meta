"""A7 Intelligence — Flask Application Factory."""

from flask import Flask

from app.db.init_db import init_db, get_connection


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.config["SECRET_KEY"] = "a7-intelligence-dev-key"
    app.config["JSON_SORT_KEYS"] = False

    # Initialize database on first request
    init_db()

    # Register blueprints
    from app.routes.dashboard import dashboard_bp
    from app.routes.api import api_bp
    from app.routes.health import health_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(health_bp)

    from app.routes.creatives import creatives_bp
    app.register_blueprint(creatives_bp, url_prefix="/api")

    from app.routes.ai_coach import ai_coach_bp
    app.register_blueprint(ai_coach_bp, url_prefix="/api")

    from app.routes.budget_intelligence import budget_bp
    app.register_blueprint(budget_bp, url_prefix="/api")

    from app.routes.growth_operations import growth_ops_bp
    app.register_blueprint(growth_ops_bp, url_prefix="/api")

    from app.routes.cross_platform import cross_platform_bp
    app.register_blueprint(cross_platform_bp, url_prefix="/api")

    from app.routes.analytics_reports import analytics_reports_bp
    app.register_blueprint(analytics_reports_bp, url_prefix="/api")

    from app.routes.automation import automation_bp
    app.register_blueprint(automation_bp, url_prefix="/api")

    # Template context processor
    @app.context_processor
    def inject_globals():
        return {"app_name": "A7 Intelligence", "version": "2.0.0"}

    return app
