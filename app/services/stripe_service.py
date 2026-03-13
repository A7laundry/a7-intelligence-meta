"""Stripe integration — checkout sessions, webhooks, billing portal."""
import os
import logging

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

# Map plan names to Stripe Price IDs (set via env vars)
PLAN_PRICE_MAP = {
    "growth": os.environ.get("STRIPE_PRICE_GROWTH", ""),
    "scale": os.environ.get("STRIPE_PRICE_SCALE", ""),
}


def is_configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


def create_checkout_session(plan_name: str, org_id: int, success_url: str, cancel_url: str):
    """Create a Stripe Checkout session for upgrading to a plan."""
    if not is_configured():
        return None, "Stripe not configured"

    price_id = PLAN_PRICE_MAP.get(plan_name.lower())
    if not price_id:
        return None, f"No Stripe price configured for plan: {plan_name}"

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={"org_id": str(org_id), "plan": plan_name},
        )
        return session, None
    except Exception as e:
        logger.exception("Stripe checkout creation failed")
        return None, str(e)


def create_billing_portal_session(stripe_customer_id: str, return_url: str):
    """Create a Stripe billing portal session for managing subscription."""
    if not is_configured() or not stripe_customer_id:
        return None, "Not configured"
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return session, None
    except Exception as e:
        logger.exception("Stripe portal session failed")
        return None, str(e)


def handle_webhook(payload: bytes, sig_header: str):
    """Parse and handle a Stripe webhook event. Returns (event_type, data) or (None, error)."""
    if not is_configured() or not STRIPE_WEBHOOK_SECRET:
        return None, "Webhook secret not configured"
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        return event["type"], event["data"]["object"]
    except Exception as e:
        logger.exception("Stripe webhook verification failed")
        return None, str(e)
