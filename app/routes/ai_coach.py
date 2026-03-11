"""AI Coach API routes — Intelligence endpoints for the dashboard."""

from flask import Blueprint, jsonify, request

from app.services.ai_coach_service import AICoachService
from app.services.account_service import AccountService

ai_coach_bp = Blueprint("ai_coach", __name__)

_service = None


def _get_service():
    global _service
    if _service is None:
        _service = AICoachService()
    return _service


@ai_coach_bp.route("/ai-coach/briefing")
def briefing():
    """Get AI-generated daily briefing."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    try:
        data = _get_service().generate_daily_briefing(days=days, platform=platform, account_id=account_id)
    except Exception as e:
        data = {"headline": "Unable to generate briefing.", "error": str(e)}
    return jsonify(data)


@ai_coach_bp.route("/ai-coach/recommendations")
def recommendations():
    """Get AI-generated recommendations."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    severity = request.args.get("severity")
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    try:
        recs = _get_service().generate_recommendations(days=days, platform=platform, account_id=account_id)
        if severity:
            recs = [r for r in recs if r["severity"] == severity]
    except Exception as e:
        recs = []
    return jsonify({"recommendations": recs, "count": len(recs)})


@ai_coach_bp.route("/ai-coach/health")
def health():
    """Get account health snapshot."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    try:
        data = _get_service().build_account_health_snapshot(days=days, platform=platform, account_id=account_id)
    except Exception as e:
        data = {"label": "unknown", "score": 0, "error": str(e)}
    return jsonify(data)


@ai_coach_bp.route("/ai-coach/refresh", methods=["POST"])
def refresh():
    """Refresh AI Coach insights (recompute)."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    try:
        svc = _get_service()
        briefing_data = svc.generate_daily_briefing(days=days, platform=platform, account_id=account_id)
        recs = svc.generate_recommendations(days=days, platform=platform, account_id=account_id)
        health_data = svc.build_account_health_snapshot(days=days, platform=platform, account_id=account_id)

        for r in recs[:5]:
            try:
                svc.save_insight(r, account_id=account_id)
            except Exception:
                pass

        return jsonify({
            "status": "ok",
            "briefing": briefing_data,
            "recommendations_count": len(recs),
            "health": health_data,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
