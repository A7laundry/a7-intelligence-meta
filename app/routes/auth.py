"""Authentication routes — login, logout, session check."""

import os
import logging
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


def _decode_jwt(token: str) -> dict | None:
    """Decode a Supabase JWT without full verification (role check only).

    Full signature verification requires fetching Supabase JWKS.
    For production hardening, replace with full RS256 verification.
    TODO: Implement RS256 verification via Supabase JWKS endpoint.
    """
    try:
        import jwt
        # Decode without verification to read claims
        # In production, verify with Supabase public key
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload
    except Exception:
        return None
