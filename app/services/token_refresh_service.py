"""Token auto-refresh service — Google OAuth2 + Meta long-lived token renewal."""
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TokenRefreshService:
    """Refreshes expired or soon-to-expire ad account tokens."""

    GOOGLE_REFRESH_THRESHOLD_HOURS = 1   # refresh if expires within 1h
    META_REFRESH_THRESHOLD_DAYS = 7      # refresh if expires within 7 days

    def refresh_all_accounts(self) -> dict:
        """Refresh tokens for all active accounts. Called by Railway Cron."""
        from app.services.account_service import AccountService
        accounts = AccountService.list_accounts()

        results = {"refreshed": 0, "skipped": 0, "failed": 0, "details": []}

        for account in accounts:
            platform = account.get("platform", "").lower()
            try:
                if platform == "google":
                    result = self._refresh_google(account)
                elif platform == "meta":
                    result = self._refresh_meta(account)
                else:
                    result = {"status": "skipped", "reason": "unknown platform"}

                results[result["status"]] = results.get(result["status"], 0) + 1
                results["details"].append({"account_id": account["id"], **result})

            except Exception as e:
                logger.exception(f"Token refresh failed for account {account.get('id')}")
                results["failed"] += 1
                results["details"].append({"account_id": account.get("id"), "status": "failed", "error": str(e)})

        return results

    def _refresh_google(self, account: dict) -> dict:
        """Exchange Google refresh_token for new access_token."""
        refresh_token = account.get("refresh_token", "")
        if not refresh_token:
            return {"status": "skipped", "reason": "no refresh_token"}

        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            return {"status": "skipped", "reason": "GOOGLE_CLIENT_ID/SECRET not configured"}

        import requests
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=15,
        )

        if resp.status_code != 200:
            return {"status": "failed", "reason": f"Google OAuth error: {resp.status_code}"}

        tokens = resp.json()
        new_access_token = tokens.get("access_token")
        expires_in = tokens.get("expires_in", 3600)

        if new_access_token:
            from app.services.account_service import AccountService
            AccountService.update_account_token(account["id"], new_access_token)
            return {"status": "refreshed", "platform": "google", "expires_in": expires_in}

        return {"status": "failed", "reason": "no access_token in response"}

    def _refresh_meta(self, account: dict) -> dict:
        """Exchange Meta short-lived token for long-lived token (60 days)."""
        access_token = account.get("access_token", "")
        if not access_token:
            return {"status": "skipped", "reason": "no access_token"}

        app_id = os.environ.get("META_APP_ID", "")
        app_secret = os.environ.get("META_APP_SECRET", "")
        if not app_id or not app_secret:
            return {"status": "skipped", "reason": "META_APP_ID/SECRET not configured"}

        import requests
        resp = requests.get(
            "https://graph.facebook.com/v18.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": access_token,
            },
            timeout=15,
        )

        if resp.status_code != 200:
            return {"status": "failed", "reason": f"Meta API error: {resp.status_code}"}

        data = resp.json()
        new_token = data.get("access_token")
        if new_token and new_token != access_token:
            from app.services.account_service import AccountService
            AccountService.update_account_token(account["id"], new_token)
            return {"status": "refreshed", "platform": "meta", "expires_in": data.get("expires_in")}

        return {"status": "skipped", "reason": "token unchanged or missing"}
