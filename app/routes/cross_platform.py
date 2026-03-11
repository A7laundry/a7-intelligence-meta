"""Cross-Platform Intelligence API routes."""

from flask import Blueprint, jsonify, request

cross_platform_bp = Blueprint("cross_platform", __name__)

_service = None


def _get_service():
    global _service
    if _service is None:
        from app.services.cross_platform_service import CrossPlatformService
        _service = CrossPlatformService()
    return _service


@cross_platform_bp.route("/platforms/summary")
def platform_summary():
    """Get per-platform aggregated metrics."""
    days = request.args.get("days", 7, type=int)
    return jsonify(_get_service().get_platform_summary(days))


@cross_platform_bp.route("/platforms/efficiency")
def platform_efficiency():
    """Get efficiency comparison across platforms."""
    days = request.args.get("days", 7, type=int)
    return jsonify(_get_service().get_channel_efficiency(days))


@cross_platform_bp.route("/platforms/opportunities")
def platform_opportunities():
    """Get cross-platform optimization opportunities."""
    days = request.args.get("days", 7, type=int)
    return jsonify(_get_service().detect_channel_opportunities(days))


@cross_platform_bp.route("/platforms/spend-share")
def platform_spend_share():
    """Get platform budget distribution."""
    days = request.args.get("days", 7, type=int)
    return jsonify(_get_service().get_spend_share(days))


@cross_platform_bp.route("/platforms/budget-evaluation")
def platform_budget_evaluation():
    """Evaluate cross-platform budget allocation."""
    days = request.args.get("days", 7, type=int)
    return jsonify(_get_service().evaluate_cross_platform_budget(days))
