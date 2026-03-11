"""Accounts API route — returns available ad accounts for the selector."""

from flask import Blueprint, jsonify, request

from app.services.account_service import AccountService

accounts_bp = Blueprint("accounts", __name__)


@accounts_bp.route("/accounts")
def list_accounts():
    """Return all ad accounts for the dashboard selector."""
    platform = request.args.get("platform")
    accounts = AccountService.get_all(platform=platform)
    return jsonify(accounts)


@accounts_bp.route("/accounts/<int:account_id>")
def get_account(account_id):
    """Return a single ad account by id."""
    acc = AccountService.get_by_id(account_id)
    if not acc:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(acc)
