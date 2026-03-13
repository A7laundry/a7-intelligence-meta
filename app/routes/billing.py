"""Billing routes — plan info, usage summary, and limit enforcement helpers."""

from flask import Blueprint, jsonify, request

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


@billing_bp.route("/billing/checkout", methods=["POST"])
def create_checkout():
    """Create Stripe checkout session to upgrade plan."""
    data = request.get_json(silent=True) or {}
    plan_name = data.get("plan", "")
    if not plan_name:
        return jsonify({"error": "plan required"}), 400

    base_url = request.host_url.rstrip("/")
    success_url = f"{base_url}/dashboard?upgraded=1"
    cancel_url = f"{base_url}/dashboard"

    from app.services.stripe_service import create_checkout_session, is_configured
    if not is_configured():
        return jsonify({"error": "Stripe not configured. Set STRIPE_SECRET_KEY."}), 503

    session, err = create_checkout_session(plan_name, DEFAULT_ORG_ID, success_url, cancel_url)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"checkout_url": session.url}), 200


@billing_bp.route("/billing/portal", methods=["POST"])
def billing_portal():
    """Create Stripe billing portal session."""
    from app.services.billing_service import BillingService
    from app.services.stripe_service import create_billing_portal_session, is_configured
    if not is_configured():
        return jsonify({"error": "Stripe not configured"}), 503

    # Get stripe_customer_id from subscription
    plan_info = BillingService.get_plan(BillingService(), DEFAULT_ORG_ID)
    customer_id = plan_info.get("stripe_customer_id")
    if not customer_id:
        return jsonify({"error": "No billing account found. Complete a checkout first."}), 404

    base_url = request.host_url.rstrip("/")
    session, err = create_billing_portal_session(customer_id, f"{base_url}/dashboard")
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"portal_url": session.url}), 200


@billing_bp.route("/billing/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events."""
    from app.services.stripe_service import handle_webhook
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")

    event_type, data = handle_webhook(payload, sig)
    if not event_type:
        return jsonify({"error": data}), 400

    # Handle key events
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data)
    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        _handle_subscription_change(data, event_type)

    return jsonify({"received": True}), 200


def _handle_checkout_completed(session):
    """Activate subscription after successful checkout."""
    try:
        org_id = int(session.get("metadata", {}).get("org_id", DEFAULT_ORG_ID))
        plan_name = session.get("metadata", {}).get("plan", "")
        customer_id = session.get("customer", "")
        from app.services.billing_service import BillingService
        BillingService.activate_plan(org_id, plan_name, customer_id)
    except Exception:
        pass  # Log but don't fail webhook


def _handle_subscription_change(subscription, event_type):
    """Handle subscription status changes."""
    try:
        customer_id = subscription.get("customer", "")
        status = subscription.get("status", "")
        from app.services.billing_service import BillingService
        BillingService.update_subscription_status(customer_id, status)
    except Exception:
        pass
