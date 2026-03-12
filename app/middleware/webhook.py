"""A7 Intelligence — HMAC Webhook Signature Validation.

Opt-in webhook signature verification via WEBHOOK_SECRET environment variable.
When WEBHOOK_SECRET is empty or not set, all validation functions are no-ops
and every request is allowed through (backward-compatible).

Supported signature headers (checked in order):
  - X-Webhook-Signature
  - X-Hub-Signature-256

Both headers must contain a hex-encoded HMAC-SHA256 digest, optionally
prefixed with "sha256=" (GitHub-style).
"""

import hashlib
import hmac
import os
from functools import wraps

from flask import request, jsonify


def verify_webhook_signature(req, secret: str) -> bool:
    """Verify the HMAC-SHA256 signature of an incoming webhook request.

    Args:
        req: The Flask request object.
        secret: The shared secret used to compute the expected signature.

    Returns:
        True if the signature is valid (or if secret is empty), False otherwise.
    """
    if not secret:
        # No secret configured — allow all requests (backward-compat).
        return True

    signature_header = (
        req.headers.get("X-Webhook-Signature", "")
        or req.headers.get("X-Hub-Signature-256", "")
    ).strip()

    if not signature_header:
        return False

    # Strip optional "sha256=" prefix.
    if signature_header.startswith("sha256="):
        signature_header = signature_header[7:]

    expected = hmac.new(
        secret.encode("utf-8"),
        req.data,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


def require_webhook_signature(func):
    """Decorator that validates the webhook HMAC signature.

    If WEBHOOK_SECRET is not configured, the decorator is a no-op and
    the wrapped function is called normally (backward-compatible).

    Returns 401 JSON if the signature is missing or invalid.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        secret = os.environ.get("WEBHOOK_SECRET", "").strip()
        if secret and not verify_webhook_signature(request, secret):
            return jsonify({"error": "Invalid webhook signature"}), 401
        return func(*args, **kwargs)

    return wrapper
