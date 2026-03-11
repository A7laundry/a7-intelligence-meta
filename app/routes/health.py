"""Health check route."""

import os
from flask import Blueprint, jsonify

from app.db.init_db import get_db_path

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """Health check endpoint."""
    db_exists = os.path.exists(get_db_path())
    return jsonify({
        "status": "ok",
        "database": "connected" if db_exists else "missing",
        "version": "2.0.0",
    })
