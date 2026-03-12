"""Billing routes — plan info, usage summary, and limit enforcement helpers."""

from flask import Blueprint, jsonify

billing_bp = Blueprint("billing", __name__)

_svc = None

# DEFAULT_ORG_ID=1 is a known limitation — multi-tenant org resolution is a future task.
DEFAULT_ORG_ID = 1


def _get_svc():
    global _svc
    if _svc is None:
        from app.services.billing_service import BillingService
        _svc = BillingService()
    return _svc


def enforce_copilot_limit():
    """Return a 429 JSON response if the Copilot query limit is exceeded, else None.

    Usage in route handlers::

        guard = enforce_copilot_limit()
        if guard:
            return guard
    """
    try:
        check = _get_svc().check_copilot_usage(org_id=DEFAULT_ORG_ID)
        if not check.get("allowed", True):
            return jsonify({
                "error": "Usage limit reached",
                "limit": check.get("limit"),
                "used": check.get("used"),
                "message": f"Copilot query limit of {check.get('limit')} reached for this billing period.",
            }), 429
    except Exception:
        # Fail open — do not block if billing DB is unavailable
        pass
    return None


def enforce_automation_limit():
    """Return a 429 JSON response if the automation run limit is exceeded, else None.

    Usage in route handlers::

        guard = enforce_automation_limit()
        if guard:
            return guard
    """
    try:
        check = _get_svc().check_automation_usage(org_id=DEFAULT_ORG_ID)
        if not check.get("allowed", True):
            return jsonify({
                "error": "Usage limit reached",
                "limit": check.get("limit"),
                "used": check.get("used"),
                "message": f"Automation run limit of {check.get('limit')} reached for this billing period.",
            }), 429
    except Exception:
        # Fail open — do not block if billing DB is unavailable
        pass
    return None


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
