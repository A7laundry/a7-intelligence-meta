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


@health_bp.route("/health/full")
def health_full():
    """Detailed system health for monitoring."""
    from datetime import datetime

    checks = {}

    # DB connectivity
    try:
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}

    # Snapshot freshness — did scheduler run today?
    try:
        conn = get_connection()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        count = conn.execute(
            "SELECT COUNT(*) FROM daily_snapshots WHERE date = ?", (today,)
        ).fetchone()[0]
        conn.close()
        checks["snapshots_today"] = {
            "status": "ok" if count > 0 else "warning",
            "count": count,
            "message": None if count > 0 else "No snapshots yet today — scheduler may not have run",
        }
    except Exception as e:
        checks["snapshots_today"] = {"status": "error", "message": str(e)}

    # Meta API connectivity
    try:
        from config_default import META_CONFIG
        token = META_CONFIG.get("access_token", "")
        checks["meta_api"] = {
            "status": "ok" if token and token not in ("", "SEU_ACCESS_TOKEN_LONGO_PRAZO") else "warning",
            "configured": bool(token),
        }
    except Exception as e:
        checks["meta_api"] = {"status": "error", "message": str(e)}

    # Google Ads connectivity
    try:
        from config_default import GOOGLE_ADS_CONFIG
        token = GOOGLE_ADS_CONFIG.get("developer_token", "")
        checks["google_ads"] = {
            "status": "ok" if token and token not in ("", "SEU_DEVELOPER_TOKEN") else "not_configured",
            "configured": bool(token),
        }
    except Exception as e:
        checks["google_ads"] = {"status": "error", "message": str(e)}

    # Account count
    try:
        conn = get_connection()
        acc_count = conn.execute(
            "SELECT COUNT(*) FROM ad_accounts WHERE status='active'"
        ).fetchone()[0]
        conn.close()
        checks["accounts"] = {"status": "ok", "active": acc_count}
    except Exception as e:
        checks["accounts"] = {"status": "error", "message": str(e)}

    overall = (
        "ok"
        if all(v.get("status") in ("ok", "not_configured") for v in checks.values())
        else "degraded"
    )

    return jsonify({
        "status": overall,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "checks": checks,
    })


@health_bp.route("/api/system/status")
def system_status():
    """Lightweight status for dashboard UI badge."""
    from datetime import datetime

    try:
        conn = get_connection()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        snap_count = conn.execute(
            "SELECT COUNT(*) FROM daily_snapshots WHERE date = ?", (today,)
        ).fetchone()[0]
        conn.close()
        return jsonify({
            "data_fresh": snap_count > 0,
            "snap_count_today": snap_count,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        return jsonify({"data_fresh": False, "error": str(e)})


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
