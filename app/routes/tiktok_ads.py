"""TikTok Ads API routes."""
from flask import Blueprint, jsonify, request
from app.services.account_service import AccountService

tiktok_bp = Blueprint("tiktok", __name__)


@tiktok_bp.route("/tiktok/connect", methods=["POST"])
def connect_tiktok():
    """Connect a TikTok Ads account."""
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token", "").strip()
    advertiser_id = data.get("advertiser_id", "").strip()
    account_name = data.get("account_name", "").strip()

    if not access_token or not advertiser_id:
        return jsonify({"error": "access_token and advertiser_id required"}), 400

    # Validate credentials
    try:
        from app.services.tiktok_ads_client import TikTokAdsClient
        client = TikTokAdsClient(access_token=access_token, advertiser_id=advertiser_id)
        info = client.validate_token()
        if not info:
            return jsonify({"error": "Invalid credentials or advertiser not found"}), 401
        display_name = account_name or info.get("name", f"TikTok {advertiser_id}")
    except Exception as e:
        return jsonify({"error": f"Validation failed: {str(e)}"}), 401

    # Store account
    try:
        account = AccountService.create_account(
            platform="tiktok",
            account_name=display_name,
            external_account_id=advertiser_id,
            access_token=access_token,
        )
        return jsonify({"ok": True, "account": account}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@tiktok_bp.route("/tiktok/insights")
def tiktok_insights():
    """Get TikTok account insights."""
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    days = request.args.get("days", 7, type=int)

    from datetime import datetime, timedelta
    end = datetime.utcnow().date()
    start = end - timedelta(days=days - 1)

    try:
        account = AccountService.get_by_id(account_id)
        if not account or account.get("platform") != "tiktok":
            return jsonify({"error": "No TikTok account found"}), 404

        from app.services.tiktok_ads_client import TikTokAdsClient
        client = TikTokAdsClient(
            access_token=account.get("access_token"),
            advertiser_id=account.get("external_account_id"),
        )
        insights = client.get_account_insights(
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
        return jsonify(insights)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
