"""Internal Jobs Routes — HTTP endpoints for Railway Cron to trigger scheduled jobs.

Replaces the daemon-thread scheduler to avoid multi-worker race conditions in
Gunicorn deployments. Each endpoint maps to one scheduled job. Railway Cron
calls these endpoints on schedule; one HTTP call = one execution regardless of
worker count.

Security: set A7_CRON_SECRET env var and configure Railway Cron to send the
header X-Cron-Secret with that value. If A7_CRON_SECRET is not set, all
requests are allowed (backward compatible for local development).
"""

import os
import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

internal_jobs_bp = Blueprint("internal_jobs", __name__)


def _check_cron_secret() -> bool:
    """Return True if the request is authorized, False otherwise."""
    expected = os.environ.get("A7_CRON_SECRET")
    if not expected:
        # Not configured — allow all (dev mode)
        return True
    provided = request.headers.get("X-Cron-Secret", "")
    return provided == expected


def _unauthorized():
    return jsonify({"error": "Unauthorized — invalid or missing X-Cron-Secret"}), 403


@internal_jobs_bp.post("/internal/jobs/snapshot")
def job_snapshot():
    """Trigger the hourly snapshot job."""
    if not _check_cron_secret():
        return _unauthorized()

    try:
        from app.services.scheduler_service import SchedulerService
        result = SchedulerService().run_snapshot_job()
        return jsonify({
            "job": "snapshot",
            "result": result,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }), 200
    except Exception as exc:
        logger.exception("[internal-jobs] snapshot failed")
        return jsonify({
            "job": "snapshot",
            "error": str(exc),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }), 500


@internal_jobs_bp.post("/internal/jobs/alerts")
def job_alerts():
    """Trigger the alert refresh job."""
    if not _check_cron_secret():
        return _unauthorized()

    try:
        from app.services.scheduler_service import SchedulerService
        result = SchedulerService().run_alert_refresh_job()
        return jsonify({
            "job": "alerts",
            "result": result,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }), 200
    except Exception as exc:
        logger.exception("[internal-jobs] alerts failed")
        return jsonify({
            "job": "alerts",
            "error": str(exc),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }), 500


@internal_jobs_bp.post("/internal/jobs/ai-refresh")
def job_ai_refresh():
    """Trigger the AI refresh + daily briefing jobs."""
    if not _check_cron_secret():
        return _unauthorized()

    results = {}
    errors = {}

    try:
        from app.services.scheduler_service import SchedulerService
        svc = SchedulerService()

        try:
            results["ai_refresh"] = svc.run_ai_refresh_job()
        except Exception as exc:
            logger.exception("[internal-jobs] ai-refresh failed")
            errors["ai_refresh"] = str(exc)

        try:
            results["daily_briefing"] = svc.run_daily_briefing_job()
        except Exception as exc:
            logger.exception("[internal-jobs] daily-briefing failed")
            errors["daily_briefing"] = str(exc)

        status = 500 if errors and not results else 200
        return jsonify({
            "job": "ai-refresh",
            "result": results,
            "errors": errors or None,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }), status
    except Exception as exc:
        logger.exception("[internal-jobs] ai-refresh init failed")
        return jsonify({
            "job": "ai-refresh",
            "error": str(exc),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }), 500


@internal_jobs_bp.post("/internal/jobs/eod")
def job_eod():
    """Trigger the end-of-day summary job."""
    if not _check_cron_secret():
        return _unauthorized()

    try:
        from app.services.scheduler_service import SchedulerService
        result = SchedulerService().run_end_of_day_summary_job()
        return jsonify({
            "job": "eod",
            "result": result,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }), 200
    except Exception as exc:
        logger.exception("[internal-jobs] eod failed")
        return jsonify({
            "job": "eod",
            "error": str(exc),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }), 500


@internal_jobs_bp.route("/internal/jobs/token-refresh", methods=["POST"])
def token_refresh():
    """Refresh expiring ad account tokens. Railway Cron: daily at 03:00 UTC."""
    if not _check_cron_secret():
        return jsonify({"error": "Unauthorized"}), 401
    from app.services.token_refresh_service import TokenRefreshService
    result = TokenRefreshService().refresh_all_accounts()
    return jsonify({"ok": True, "result": result})


@internal_jobs_bp.route("/internal/jobs/content-insights", methods=["POST"])
def content_insights_job():
    """Generate content performance insights. Railway Cron: daily at 07:00 UTC."""
    if not _check_cron_secret():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from app.services.content_intelligence_service import ContentIntelligenceService
        result = ContentIntelligenceService().run_daily_insights()
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        logger.exception("[internal-jobs] content-insights failed")
        return jsonify({"ok": False, "error": str(e)}), 500
