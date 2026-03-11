"""Creative Intelligence API routes."""

from flask import Blueprint, jsonify, request

from app.services.creative_service import CreativeService

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

    creatives = _get_service().get_creatives(
        days=days, status=status, campaign_id=campaign, fatigue_only=fatigue_only
    )
    return jsonify({"creatives": creatives, "count": len(creatives)})


@creatives_bp.route("/creatives/top")
def top_creatives():
    """Get top performing creatives."""
    days = request.args.get("days", 7, type=int)
    limit = request.args.get("limit", 5, type=int)
    top = _get_service().get_top_creatives(days=days, limit=limit)
    return jsonify({"creatives": top})


@creatives_bp.route("/creatives/fatigue")
def fatigued_creatives():
    """Get creatives showing fatigue signals."""
    days = request.args.get("days", 7, type=int)
    fatigued = _get_service().get_fatigued_creatives(days=days)
    return jsonify({"creatives": fatigued, "count": len(fatigued)})


@creatives_bp.route("/creatives/summary")
def creative_summary():
    """Get creative intelligence summary."""
    days = request.args.get("days", 7, type=int)
    summary = _get_service().get_summary(days=days)
    return jsonify(summary)


@creatives_bp.route("/creatives/collect", methods=["POST"])
def collect_creatives():
    """Trigger creative data collection from Meta API."""
    result = _get_service().collect_creatives()
    return jsonify(result)
