"""Authentication routes — login, logout, session check."""

import os
import logging
import jwt
from flask import Blueprint, request, jsonify, session, redirect, url_for

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/auth/login", methods=["GET"])
def login_page():
    """Serve the login page."""
    from flask import render_template
    # If already authenticated, redirect to dashboard
    if session.get("access_token"):
        return redirect(url_for("dashboard.index"))
    return render_template("login.html")


@auth_bp.route("/auth/login", methods=["POST"])
def login():
    """Exchange email/password for Supabase JWT and store in session."""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()

    if not supabase_url or not supabase_anon_key:
        return jsonify({"error": "Auth not configured"}), 503

    import requests as http
    try:
        resp = http.post(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers={
                "apikey": supabase_anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
            timeout=10,
        )
        if resp.status_code != 200:
            error_data = resp.json() if resp.content else {}
            return jsonify({"error": error_data.get("error_description", "Invalid credentials")}), 401

        tokens = resp.json()
        session["access_token"] = tokens["access_token"]
        session["refresh_token"] = tokens.get("refresh_token", "")
        session.permanent = True
        return jsonify({"ok": True}), 200

    except Exception as exc:
        logger.exception("Login failed")
        return jsonify({"error": "Authentication service unavailable"}), 503


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """Clear session and log out."""
    session.clear()
    return jsonify({"ok": True}), 200


@auth_bp.route("/auth/me")
def me():
    """Return current user info from JWT, or 401 if not authenticated."""
    token = session.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return jsonify({"authenticated": False}), 401

    payload = _decode_jwt(token)
    if not payload:
        return jsonify({"authenticated": False}), 401

    return jsonify({
        "authenticated": True,
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
    }), 200


_SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


def _decode_jwt(token: str):
    """Verify and decode a Supabase JWT.

    Supabase signs JWTs with HS256 using the project's JWT Secret
    (found in Supabase project settings → API → JWT Secret).

    Graceful mode: if SUPABASE_JWT_SECRET is not set, the token is decoded
    without signature verification so existing deployments are not locked out.
    Set SUPABASE_JWT_SECRET in Railway (or your environment) to enable full
    verification.
    """
    if not token:
        return None

    secret = os.environ.get("SUPABASE_JWT_SECRET", _SUPABASE_JWT_SECRET)

    if secret:
        # Full HS256 verification — production path
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},  # Supabase sets aud=authenticated
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.debug("JWT expired")
            return None
        except jwt.InvalidTokenError as exc:
            logger.debug("JWT invalid: %s", exc)
            return None
    else:
        # Graceful fallback — no secret configured, skip signature check
        # WARNING: tokens are NOT verified in this mode. Set SUPABASE_JWT_SECRET.
        logger.warning(
            "SUPABASE_JWT_SECRET not set — JWT signature verification is DISABLED. "
            "Set this env var in Railway to enable secure token validation."
        )
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=["HS256"],
            )
            return payload
        except Exception:
            return None
