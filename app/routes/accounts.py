"""Accounts API route — returns available ad accounts for the selector."""

from flask import Blueprint, jsonify, request

from app.services.account_service import AccountService

accounts_bp = Blueprint("accounts", __name__)

_overview_service = None


def _get_overview_service():
    global _overview_service
    if _overview_service is None:
        from app.services.cross_account_service import CrossAccountService
        _overview_service = CrossAccountService()
    return _overview_service


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


@accounts_bp.route("/accounts/overview")
def accounts_overview():
    """Return aggregated metrics across all accounts for the cross-account overview."""
    days = request.args.get("days", 7, type=int)
    try:
        data = _get_overview_service().build_overview(days=days)
    except Exception as e:
        data = {"accounts": [], "insights": {}, "totals": {}, "spend_share": {}, "error": str(e)}
    return jsonify(data)


@accounts_bp.route("/accounts/<int:account_id>/status")
def account_status(account_id):
    """Return sync status for a single account."""
    acc = AccountService.get_by_id(account_id)
    if not acc:
        return jsonify({"error": "Account not found"}), 404
    try:
        from app.services.cross_account_service import CrossAccountService
        svc = CrossAccountService()
        data = svc.get_account_status(account_id)
    except Exception as e:
        data = {"error": str(e)}
    return jsonify(data)
