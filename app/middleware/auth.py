"""A7 Intelligence — Authentication Middleware.

Priority order for authentication:
1. Supabase JWT (SUPABASE_URL + SUPABASE_ANON_KEY configured)
   - Checks Flask session["access_token"] (browser)
   - OR Authorization: Bearer <token> header (API clients)
2. API Key fallback (A7_API_KEY configured, no Supabase)
   - X-API-Key header or ?api_key= query param
3. Open access (neither configured — dev mode)

Exempt paths: /, /health, /health/detailed, /static/*, /auth/*
"""

import os
import logging

from flask import Flask, request, jsonify, session

logger = logging.getLogger(__name__)

_EXEMPT_PATHS = {"/", "/health", "/health/detailed"}
_EXEMPT_PREFIXES = ("/static/", "/auth/")


def _is_exempt(path: str) -> bool:
    return path in _EXEMPT_PATHS or any(path.startswith(p) for p in _EXEMPT_PREFIXES)


def _get_bearer_token():
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def _validate_jwt(token: str) -> bool:
    """Validate a Supabase JWT (signature-less decode for role check)."""
    if not token:
        return False
    try:
        import jwt
        payload = jwt.decode(token, options={"verify_signature": False})
        # Verify it's a Supabase token with a subject
        return bool(payload.get("sub"))
    except Exception:
        return False


def register_auth_middleware(app: Flask) -> None:
    """Attach authentication middleware to the Flask app."""

    @app.before_request
    def check_auth():
        if _is_exempt(request.path):
            return None

        supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        api_key = os.environ.get("A7_API_KEY", "").strip()

        # Mode 1: Supabase Auth
        if supabase_url:
            # Try session token (browser) then Authorization header (API)
            token = session.get("access_token") or _get_bearer_token()
            if token and _validate_jwt(token):
                return None
            # Not authenticated → redirect browser to login, 401 for API
            if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                return jsonify({"error": "Unauthorized"}), 401
            # For browser requests to /api/* return 401 JSON
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            from flask import redirect, url_for
            return redirect(url_for("auth.login_page"))

        # Mode 2: API Key fallback
        if api_key:
            provided = (
                request.headers.get("X-API-Key", "").strip()
                or request.args.get("api_key", "").strip()
            )
            if provided != api_key:
                return jsonify({"error": "Unauthorized"}), 401
            return None

        # Mode 3: Open access (dev)
        return None
