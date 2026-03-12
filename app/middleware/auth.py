"""A7 Intelligence — API Key Authentication Middleware.

Opt-in authentication via A7_API_KEY environment variable.
When A7_API_KEY is empty or not set, this middleware is a no-op and all
requests pass through unchanged (backward-compatible).

When A7_API_KEY is set, all requests to /api/* paths must include either:
  - X-API-Key: <key>  (request header)
  - ?api_key=<key>    (query parameter)

Exempt paths (always allowed regardless of key):
  /, /health, /health/detailed, /static/*
"""

import os

from flask import Flask, request, jsonify


# Paths that are always accessible without an API key.
_EXEMPT_PATHS = {"/", "/health", "/health/detailed"}
_STATIC_PREFIX = "/static/"


def _is_exempt(path: str) -> bool:
    """Return True if the request path is exempt from API key checks."""
    return path in _EXEMPT_PATHS or path.startswith(_STATIC_PREFIX)


def register_auth_middleware(app: Flask) -> None:
    """Attach the API key before_request handler to *app*.

    If A7_API_KEY is not configured, the handler is registered but
    immediately returns None (no-op) on every request.
    """

    @app.before_request
    def check_api_key():
        api_key = os.environ.get("A7_API_KEY", "").strip()

        # Feature disabled — open access, backward-compatible.
        if not api_key:
            return None

        # Exempt paths are always allowed.
        if _is_exempt(request.path):
            return None

        # Check header first, then query param.
        provided = (
            request.headers.get("X-API-Key", "").strip()
            or request.args.get("api_key", "").strip()
        )

        if provided != api_key:
            return jsonify({"error": "Unauthorized"}), 401

        return None
