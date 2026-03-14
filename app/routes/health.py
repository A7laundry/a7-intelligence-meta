"""Health check routes."""

import os
from flask import Blueprint, jsonify

from app.db.init_db import get_db_path, get_connection
from app.version import VERSION

health_bp = Blueprint("health", __name__)


def _check_db_connectivity() -> bool:
    """Return True if the configured database is accessible.

    On PostgreSQL (DATABASE_URL set): attempt a lightweight query.
    On SQLite: check the file exists.
    """
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        try:
            conn = get_connection()
            conn.execute("SELECT 1").fetchone()
            conn.close()
            return True
        except Exception:
            return False
    # SQLite path
    return os.path.exists(get_db_path())


@health_bp.route("/health")
def health():
    """Basic health check — used by Railway and load balancers."""
    db_ok = _check_db_connectivity()

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


@health_bp.route("/health/google-ads")
def health_google_ads():
    """Google Ads connectivity check — initializes client and makes a lightweight API call."""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    try:
        from config_default import GOOGLE_ADS_CONFIG
        customer_id = GOOGLE_ADS_CONFIG.get("customer_id", "")

        from app.services.google_ads_client import GoogleAdsClientWrapper
        wrapper = GoogleAdsClientWrapper()

        if not wrapper.available:
            return jsonify({"status": "error", "message": "Google Ads client not available — check credentials"}), 503

        # Lightweight test call: list campaigns with LIMIT 1
        campaigns = wrapper.client.list_campaigns()
        return jsonify({
            "status": "ok",
            "customer_id": customer_id,
            "campaigns_found": len(campaigns),
        }), 200

    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503


@health_bp.route("/health/detailed")
def health_detailed():
    """Detailed health check with diagnostics."""
    database_url = os.environ.get("DATABASE_URL", "").strip()
    db_path = get_db_path()
    db_ok = _check_db_connectivity()

    if database_url:
        db_info = {
            "mode": "postgresql",
            "connected": db_ok,
        }
        storage_info = {"mode": "postgresql", "persistent": True}
    else:
        db_writable = False
        if db_ok:
            try:
                db_writable = os.access(db_path, os.W_OK)
            except Exception:
                pass
        data_dir = os.path.dirname(db_path)
        db_info = {
            "mode": "sqlite",
            "path": db_path,
            "exists": db_ok,
            "writable": db_writable,
        }
        storage_info = {
            "mode": "sqlite",
            "data_dir": data_dir,
            "writable": os.access(data_dir, os.W_OK) if os.path.exists(data_dir) else False,
        }

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
        "database": db_info,
        "storage": storage_info,
        "scheduler": {
            "disabled_by_env": scheduler_disabled,
            **sched_info,
        },
    })
