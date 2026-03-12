"""Billing routes — plan info and usage summary."""

from flask import Blueprint, jsonify

billing_bp = Blueprint("billing", __name__)

_svc = None


def _get_svc():
    global _svc
    if _svc is None:
        from app.services.billing_service import BillingService
        _svc = BillingService()
    return _svc


@billing_bp.route("/billing/plan", methods=["GET"])
def get_plan():
    """GET /api/billing/plan — current plan and subscription."""
    try:
        return jsonify(_get_svc().get_plan())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@billing_bp.route("/billing/usage", methods=["GET"])
def get_usage():
    """GET /api/billing/usage — plan usage summary for dashboard panel."""
    try:
        return jsonify(_get_svc().get_plan_usage_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
