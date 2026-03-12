"""Health check routes."""

import os
from flask import Blueprint, jsonify

from app.db.init_db import get_db_path, get_connection
from app.version import VERSION

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """Basic health check — used by Railway and load balancers."""
    db_path = get_db_path()
    db_ok = os.path.exists(db_path)

    scheduler_disabled = os.environ.get("A7_DISABLE_SCHEDULER") == "1"
    try:
        from app.services.scheduler_loop_service import get_scheduler_status
        sched = get_scheduler_status()
        scheduler_running = sched.get("running", False)
    except Exception:
        scheduler_running = False

    status = "ok" if db_ok else "degraded"
    return jsonify({
        "status": status,
        "version": VERSION,
        "database": "connected" if db_ok else "missing",
        "scheduler_enabled": not scheduler_disabled,
        "scheduler_running": scheduler_running,
    }), 200 if status == "ok" else 503


@health_bp.route("/health/tokens")
def health_tokens():
    """Token/credential presence check — no external API calls made."""
    result = {}

    # META_ACCESS_TOKEN
    meta_token = bool(os.environ.get("META_ACCESS_TOKEN", "").strip())
    meta_info = {"token_present": meta_token}
    if meta_token:
        try:
            conn = get_connection()
            try:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM ad_accounts").fetchone()
                meta_info["accounts_in_db"] = row["cnt"] if row else 0
            finally:
                conn.close()
        except Exception as exc:
            meta_info["accounts_in_db"] = 0
            meta_info["db_error"] = str(exc)
    result["meta"] = meta_info

    # DEEPSEEK_API_KEY
    result["deepseek"] = {"token_present": bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())}

    # ANTHROPIC_API_KEY
    result["anthropic"] = {"token_present": bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())}

    # GOOGLE_ADS_DEVELOPER_TOKEN
    result["google_ads"] = {"token_present": bool(os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip())}

    return jsonify(result), 200


@health_bp.route("/health/detailed")
def health_detailed():
    """Detailed health check with diagnostics."""
    db_path = get_db_path()
    db_ok = os.path.exists(db_path)
    db_writable = False
    if db_ok:
        try:
            db_writable = os.access(db_path, os.W_OK)
        except Exception:
            pass
    data_dir = os.path.dirname(db_path)
    data_dir_writable = os.access(data_dir, os.W_OK) if os.path.exists(data_dir) else False

    scheduler_disabled = os.environ.get("A7_DISABLE_SCHEDULER") == "1"
    sched_info = {}
    try:
        from app.services.scheduler_loop_service import get_scheduler_status
        sched_info = get_scheduler_status()
    except Exception as exc:
        sched_info = {"error": str(exc)}

    env = os.environ.get("RAILWAY_ENVIRONMENT", os.environ.get("FLASK_ENV", "development"))

    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "version": VERSION,
        "environment": env,
        "database": {
            "path": db_path,
            "exists": db_ok,
            "writable": db_writable,
        },
        "storage": {
            "data_dir": data_dir,
            "writable": data_dir_writable,
        },
        "scheduler": {
            "disabled_by_env": scheduler_disabled,
            **sched_info,
        },
    })
