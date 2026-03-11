"""Growth Operations & Automation API routes."""

from flask import Blueprint, jsonify, request

from app.services.growth_score_service import GrowthScoreService
from app.services.scheduler_service import SchedulerService
from app.services.automation_guardrails_service import AutomationGuardrailsService
from app.services.account_service import AccountService

growth_ops_bp = Blueprint("growth_ops", __name__)

_growth = None
_scheduler = None
_guardrails = None


def _get_growth():
    global _growth
    if _growth is None:
        _growth = GrowthScoreService()
    return _growth


def _get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler


def _get_guardrails():
    global _guardrails
    if _guardrails is None:
        _guardrails = AutomationGuardrailsService()
    return _guardrails


# ── Growth Score ─────────────────────────────────────────────

@growth_ops_bp.route("/growth-score")
def growth_score():
    """Get unified growth score."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    try:
        data = _get_growth().build_growth_score(days=days, platform=platform, account_id=account_id)
    except Exception as e:
        data = {"score": 0, "label": "unknown", "error": str(e)}
    return jsonify(data)


# ── Scheduled Operations ────────────────────────────────────

@growth_ops_bp.route("/operations/status")
def ops_status():
    """Get latest status for each operation type."""
    try:
        status = _get_scheduler().get_operations_status()
    except Exception:
        status = {}
    return jsonify({"operations": status})


@growth_ops_bp.route("/operations/history")
def ops_history():
    """Get recent operations log."""
    limit = request.args.get("limit", 50, type=int)
    try:
        history = _get_scheduler().get_operations_history(limit=limit)
    except Exception:
        history = []
    return jsonify({"history": history, "count": len(history)})


@growth_ops_bp.route("/operations/run/snapshot", methods=["POST"])
def run_snapshot():
    """Run snapshot job."""
    result = _get_scheduler().run_snapshot_job()
    return jsonify(result)


@growth_ops_bp.route("/operations/run/ai-refresh", methods=["POST"])
def run_ai_refresh():
    """Run AI refresh job."""
    result = _get_scheduler().run_ai_refresh_job()
    return jsonify(result)


@growth_ops_bp.route("/operations/run/alerts", methods=["POST"])
def run_alerts():
    """Run alert refresh job."""
    result = _get_scheduler().run_alert_refresh_job()
    return jsonify(result)


@growth_ops_bp.route("/operations/run/daily-briefing", methods=["POST"])
def run_daily_briefing():
    """Run daily briefing job."""
    result = _get_scheduler().run_daily_briefing_job()
    return jsonify(result)


@growth_ops_bp.route("/operations/run/end-of-day", methods=["POST"])
def run_end_of_day():
    """Run end-of-day summary job."""
    result = _get_scheduler().run_end_of_day_summary_job()
    return jsonify(result)


# ── Automation ───────────────────────────────────────────────

@growth_ops_bp.route("/automation/proposals")
def automation_proposals():
    """Get current action proposals with guardrail evaluation."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    try:
        svc = _get_guardrails()
        proposals = svc.generate_proposals(days=days, platform=platform)
        result = svc.apply_guardrails(proposals)
    except Exception as e:
        result = {"allowed": [], "blocked": [], "error": str(e)}
    return jsonify(result)


@growth_ops_bp.route("/automation/evaluate", methods=["POST"])
def automation_evaluate():
    """Recompute proposals and apply guardrails."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    try:
        svc = _get_guardrails()
        proposals = svc.generate_proposals(days=days, platform=platform)
        result = svc.apply_guardrails(proposals)
    except Exception as e:
        result = {"allowed": [], "blocked": [], "error": str(e)}
    return jsonify(result)


@growth_ops_bp.route("/automation/guardrails")
def guardrails_config():
    """Get current guardrails configuration."""
    try:
        config = _get_guardrails().get_guardrails_config()
    except Exception:
        config = {"guardrails_active": False}
    return jsonify(config)
