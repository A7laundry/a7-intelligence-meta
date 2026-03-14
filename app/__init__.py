"""A7 Intelligence — Flask Application Factory."""

import atexit
import fcntl
import os

from flask import Flask

from app.db.init_db import init_db, get_connection
from app.version import VERSION


def _is_scheduler_leader() -> bool:
    """Return True only for the first worker that acquires the scheduler lock.

    Uses a non-blocking exclusive flock on a well-known path so that only one
    Gunicorn worker runs the background scheduler at a time.  The lock is held
    for the lifetime of the process; if the leader dies, the next worker that
    happens to call this function will pick it up.
    """
    if os.environ.get("A7_DISABLE_SCHEDULER") == "1":
        return False
    lock_path = "/tmp/a7_scheduler.lock"
    try:
        lock_fd = open(lock_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Keep fd open for the life of the process — lock released on exit.
        atexit.register(lambda: (fcntl.flock(lock_fd, fcntl.LOCK_UN), lock_fd.close()))
        return True
    except (IOError, OSError):
        return False


def create_app():
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        if os.environ.get("FLASK_ENV") == "production" or os.environ.get("RAILWAY_ENVIRONMENT"):
            # On Railway without SECRET_KEY set, generate a stable-per-process key
            # and warn loudly — user should set SECRET_KEY in Railway env vars.
            import warnings
            warnings.warn(
                "SECRET_KEY env var is not set. Sessions will not persist across "
                "restarts. Set SECRET_KEY in Railway environment variables.",
                RuntimeWarning,
                stacklevel=2,
            )
        secret_key = "a7-intelligence-dev-key"

    app.config["SECRET_KEY"] = secret_key
    app.config["JSON_SORT_KEYS"] = False
    app.config["VERSION"] = VERSION

    # Initialize database on first request
    init_db()

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.api import api_bp
    from app.routes.health import health_bp

    app.register_blueprint(auth_bp)
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

    from app.routes.accounts import accounts_bp
    app.register_blueprint(accounts_bp, url_prefix="/api")

    from app.routes.copilot import copilot_bp
    app.register_blueprint(copilot_bp, url_prefix="/api")

    from app.routes.billing import billing_bp
    app.register_blueprint(billing_bp, url_prefix="/api")

    from app.routes.content import content_bp
    app.register_blueprint(content_bp, url_prefix="/api")

    from app.routes.publishing import publishing_bp
    app.register_blueprint(publishing_bp, url_prefix="/api")

    from app.routes.calendar import calendar_bp
    app.register_blueprint(calendar_bp, url_prefix="/api")

    from app.routes.content_intelligence import content_intelligence_bp
    app.register_blueprint(content_intelligence_bp, url_prefix="/api")

    from app.routes.command_center import cc_bp
    app.register_blueprint(cc_bp, url_prefix="/api")

    from app.routes.internal_jobs import internal_jobs_bp
    app.register_blueprint(internal_jobs_bp, url_prefix="/api")

    from app.routes.orgs import orgs_bp
    app.register_blueprint(orgs_bp, url_prefix="/api")

    from app.routes.tiktok_ads import tiktok_bp
    app.register_blueprint(tiktok_bp, url_prefix="/api")

    from app.routes.reports import reports_bp
    app.register_blueprint(reports_bp, url_prefix="/api")

    from app.routes.pulse import pulse_bp
    app.register_blueprint(pulse_bp)

    from app.routes.launch import launch_bp
    app.register_blueprint(launch_bp, url_prefix="/api")

    # Register API key middleware (no-op if A7_API_KEY not set)
    from app.middleware.auth import register_auth_middleware
    register_auth_middleware(app)

    # Start background publishing scheduler (skip during testing or when disabled).
    # _is_scheduler_leader() uses a non-blocking flock so only one Gunicorn
    # worker acquires the lock — preventing triple writes to SQLite on Railway.
    scheduler_enabled = (
        not app.testing
        and _is_scheduler_leader()
    )
    if scheduler_enabled:
        from app.services.scheduler_loop_service import start_publishing_scheduler
        start_publishing_scheduler(app)

    env_label = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("FLASK_ENV", "development"))
    print(
        f"[A7] v{VERSION} started | env={env_label} | "
        f"scheduler={'enabled' if scheduler_enabled else 'disabled'}"
    )

    # Template context processor
    @app.context_processor
    def inject_globals():
        return {"app_name": "A7 Intelligence", "version": VERSION}

    return app
