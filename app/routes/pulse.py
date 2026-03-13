"""
Pulse API — mark-reviewed, mark-resolved, insight history.
"""

from flask import Blueprint, jsonify, request

from app.services.account_service import AccountService
from app.services.pulse_service import PulseService

pulse_bp = Blueprint("pulse", __name__)


@pulse_bp.route("/api/insights/<int:insight_id>/reviewed", methods=["POST"])
def mark_reviewed(insight_id: int):
    account_id = AccountService.resolve_account_id(
        (request.get_json(silent=True) or {}).get("account_id")
        or request.args.get("account_id")
    )
    if not account_id:
        return jsonify({"error": "account_id required"}), 400

    ok = PulseService.mark_reviewed(insight_id, account_id)
    if not ok:
        return jsonify({"error": "not found or state not eligible"}), 404
    return jsonify({"status": "reviewed"})


@pulse_bp.route("/api/insights/<int:insight_id>/resolved", methods=["POST"])
def mark_resolved(insight_id: int):
    account_id = AccountService.resolve_account_id(
        (request.get_json(silent=True) or {}).get("account_id")
        or request.args.get("account_id")
    )
    if not account_id:
        return jsonify({"error": "account_id required"}), 400

    ok = PulseService.mark_resolved(insight_id, account_id)
    if not ok:
        return jsonify({"error": "not found or already resolved"}), 404
    return jsonify({"status": "resolved"})


@pulse_bp.route("/api/insights/<int:insight_id>/history", methods=["GET"])
def get_history(insight_id: int):
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    if not account_id:
        return jsonify({"error": "account_id required"}), 400

    history = PulseService.get_history(insight_id, account_id)
    return jsonify({"history": history})
