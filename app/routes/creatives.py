"""Creative Intelligence API routes."""

from flask import Blueprint, jsonify, request

from app.services.creative_service import CreativeService
from app.services.account_service import AccountService

creatives_bp = Blueprint("creatives", __name__)

_service = None


def _get_service():
    global _service
    if _service is None:
        _service = CreativeService()
    return _service


@creatives_bp.route("/creatives")
def list_creatives():
    """List all creatives with metrics and scores."""
    days = request.args.get("days", 7, type=int)
    status = request.args.get("status")
    campaign = request.args.get("campaign")
    fatigue_only = request.args.get("fatigue_only", "false").lower() == "true"
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))

    creatives = _get_service().get_creatives(
        days=days, status=status, campaign_id=campaign, fatigue_only=fatigue_only, account_id=account_id
    )
    return jsonify({"creatives": creatives, "count": len(creatives)})


@creatives_bp.route("/creatives/top")
def top_creatives():
    """Get top performing creatives."""
    days = request.args.get("days", 7, type=int)
    limit = request.args.get("limit", 5, type=int)
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    top = _get_service().get_top_creatives(days=days, limit=limit, account_id=account_id)
    return jsonify({"creatives": top})


@creatives_bp.route("/creatives/fatigue")
def fatigued_creatives():
    """Get creatives showing fatigue signals."""
    days = request.args.get("days", 7, type=int)
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    fatigued = _get_service().get_fatigued_creatives(days=days, account_id=account_id)
    return jsonify({"creatives": fatigued, "count": len(fatigued)})


@creatives_bp.route("/creatives/summary")
def creative_summary():
    """Get creative intelligence summary."""
    days = request.args.get("days", 7, type=int)
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    summary = _get_service().get_summary(days=days, account_id=account_id)
    return jsonify(summary)


@creatives_bp.route("/creatives/collect", methods=["POST"])
def collect_creatives():
    """Trigger creative data collection from Meta API."""
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    result = _get_service().collect_creatives(account_id=account_id)
    return jsonify(result)
