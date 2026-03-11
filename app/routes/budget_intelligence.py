"""Budget Intelligence & Alerts API routes."""

from flask import Blueprint, jsonify, request

from app.services.budget_intelligence_service import BudgetIntelligenceService
from app.services.alerts_service import AlertsService

budget_bp = Blueprint("budget", __name__)

_bi_service = None
_alerts_service = None


def _get_bi():
    global _bi_service
    if _bi_service is None:
        _bi_service = BudgetIntelligenceService()
    return _bi_service


def _get_alerts():
    global _alerts_service
    if _alerts_service is None:
        _alerts_service = AlertsService()
    return _alerts_service


# ── Budget Intelligence ─────────────────────────────────────

@budget_bp.route("/budget/summary")
def budget_summary():
    """Get budget allocation summary with efficiency score."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    try:
        allocation = _get_bi().analyze_budget_allocation(days, platform)
        efficiency = _get_bi().compute_efficiency_score(days, platform)
        allocation["efficiency_score"] = efficiency["score"]
        allocation["efficiency_components"] = efficiency["components"]
    except Exception as e:
        allocation = {"error": str(e), "total_spend": 0}
    return jsonify(allocation)


@budget_bp.route("/budget/opportunities")
def budget_opportunities():
    """Get scaling opportunities."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    try:
        opps = _get_bi().detect_scaling_opportunities(days, platform)
    except Exception:
        opps = []
    return jsonify({"opportunities": opps, "count": len(opps)})


@budget_bp.route("/budget/waste")
def budget_waste():
    """Get waste campaigns."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    try:
        waste = _get_bi().detect_budget_waste(days, platform)
    except Exception:
        waste = {"waste_spend": 0, "campaigns": []}
    return jsonify(waste)


@budget_bp.route("/budget/pacing")
def budget_pacing():
    """Get budget pacing analysis."""
    days = request.args.get("days", 1, type=int)
    platform = request.args.get("platform")
    try:
        pacing = _get_bi().monitor_budget_pacing(days, platform)
    except Exception:
        pacing = {"campaigns": []}
    return jsonify(pacing)


@budget_bp.route("/budget/anomalies")
def budget_anomalies():
    """Get spend anomalies."""
    days = request.args.get("days", 7, type=int)
    try:
        result = _get_bi().detect_spend_anomalies(days)
    except Exception:
        result = {"anomalies": []}
    return jsonify(result)


# ── Alerts ───────────────────────────────────────────────────

@budget_bp.route("/alerts")
def list_alerts():
    """Get active alerts."""
    severity = request.args.get("severity")
    limit = request.args.get("limit", 50, type=int)
    try:
        alerts = _get_alerts().get_active_alerts(limit=limit, severity=severity)
    except Exception:
        alerts = []
    return jsonify({"alerts": alerts, "count": len(alerts)})


@budget_bp.route("/alerts/history")
def alert_history():
    """Get alert history."""
    days = request.args.get("days", 7, type=int)
    try:
        alerts = _get_alerts().get_alert_history(days=days)
    except Exception:
        alerts = []
    return jsonify({"alerts": alerts, "count": len(alerts)})


@budget_bp.route("/alerts/refresh", methods=["POST"])
def refresh_alerts():
    """Recompute and persist alerts."""
    days = request.args.get("days", 7, type=int)
    try:
        new_alerts = _get_alerts().generate_all_alerts(days=days)
        return jsonify({"status": "ok", "new_alerts": len(new_alerts), "alerts": new_alerts})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@budget_bp.route("/alerts/<int:alert_id>/resolve", methods=["POST"])
def resolve_alert(alert_id):
    """Resolve an alert."""
    try:
        success = _get_alerts().resolve_alert(alert_id)
        return jsonify({"status": "ok" if success else "not_found"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
