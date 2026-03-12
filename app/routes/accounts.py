"""Accounts API — registry, connection, status, and cross-account overview."""

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
    # Never expose raw credentials in the list
    safe = []
    for a in accounts:
        row = dict(a)
        row.pop("access_token", None)
        row.pop("developer_token", None)
        row.pop("refresh_token", None)
        safe.append(row)
    return jsonify(safe)


@accounts_bp.route("/accounts/connect", methods=["POST"])
def connect_account():
    """Connect a new Meta Ads or Google Ads account.

    Body (JSON):
        platform              (str, required): 'meta' | 'google'
        account_name          (str, optional): display name override

        Meta fields:
            external_account_id  (str, required): act_xxxxx
            access_token         (str, required)

        Google fields:
            customer_id          (str, required)
            developer_token      (str, required)
            refresh_token        (str, required)

    Returns:
        201 {"success": true,  "account": {...}}
        400 {"success": false, "error": str}
    """
    body = request.get_json(silent=True) or {}
    platform = (body.get("platform") or "").strip().lower()

    if platform not in ("meta", "google"):
        return jsonify({"success": False,
                        "error": "platform must be 'meta' or 'google'"}), 400

    try:
        from app.services.onboarding_service import OnboardingService
        svc = OnboardingService()

        if platform == "meta":
            ext_id = (body.get("external_account_id") or "").strip()
            token = (body.get("access_token") or "").strip()
            if not ext_id or not token:
                return jsonify({"success": False,
                                "error": "external_account_id and access_token are required"}), 400
            result = svc.connect_meta(ext_id, token,
                                      account_name=(body.get("account_name") or "").strip() or None)
        else:
            cid = (body.get("customer_id") or "").strip()
            dev_tok = (body.get("developer_token") or "").strip()
            ref_tok = (body.get("refresh_token") or "").strip()
            if not cid or not dev_tok or not ref_tok:
                return jsonify({"success": False,
                                "error": "customer_id, developer_token, and refresh_token are required"}), 400
            result = svc.connect_google(cid, dev_tok, ref_tok,
                                        account_name=(body.get("account_name") or "").strip() or None)

    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

    if result.get("success"):
        # Strip credentials from response
        if result.get("account"):
            acc = dict(result["account"])
            acc.pop("access_token", None)
            acc.pop("developer_token", None)
            acc.pop("refresh_token", None)
            result["account"] = acc
        return jsonify(result), 201
    return jsonify(result), 400


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


@accounts_bp.route("/accounts/health")
def accounts_health():
    """Return per-account health snapshot for all accounts."""
    try:
        data = _get_overview_service().build_health_overview()
    except Exception as e:
        data = {"accounts": [], "error": str(e)}
    return jsonify(data)


@accounts_bp.route("/accounts/<int:account_id>/status")
def account_status(account_id):
    """Return sync status for a single account.

    Response:
        last_sync         — ISO timestamp of last successful sync
        campaign_count    — distinct active campaigns
        spend_7d          — total spend over last 7 days
        alerts_count      — unresolved active alerts
        (plus extended fields from cross_account_service)
    """
    acc = AccountService.get_by_id(account_id)
    if not acc:
        return jsonify({"error": "Account not found"}), 404
    try:
        from app.services.cross_account_service import CrossAccountService
        svc = CrossAccountService()
        data = svc.get_account_status(account_id)
        # Merge last_sync from account record (more accurate than last snapshot date)
        data["last_sync"] = acc.get("last_sync") or data.get("last_snapshot")
        data.setdefault("campaign_count", data.get("campaigns_count", 0))
        data.setdefault("alerts_count", data.get("alerts_active", 0))
    except Exception as exc:
        data = {
            "error": str(exc),
            "last_sync": acc.get("last_sync"),
            "campaign_count": 0,
            "spend_7d": 0,
            "alerts_count": 0,
        }
    return jsonify(data)
