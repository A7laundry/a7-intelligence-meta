"""Metrics Service — Campaign-level operations via existing API clients."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class MetricsService:
    """Wraps existing MetaAdsClient for use in Flask routes."""

    def __init__(self):
        self.meta_client = None
        self.meta_available = False
        self._init()

    def _init(self):
        try:
            from config_default import META_CONFIG
            if META_CONFIG.get("access_token") and META_CONFIG["access_token"] != "SEU_ACCESS_TOKEN_LONGO_PRAZO":
                from meta_client import MetaAdsClient
                self.meta_client = MetaAdsClient()
                self.meta_available = True
        except Exception:
            pass

    @classmethod
    def for_account(cls, account_id: int) -> "MetricsService":
        """Return a MetricsService configured with the token and account ID from the DB."""
        svc = cls.__new__(cls)
        svc.meta_client = None
        svc.meta_available = False
        try:
            from app.services.account_service import AccountService
            from meta_client import MetaAdsClient
            account = AccountService.get_by_id(account_id)
            if account and account.get("access_token"):
                client = MetaAdsClient(access_token=account["access_token"])
                ext_id = account.get("external_account_id")
                if ext_id:
                    client.ad_account_id = ext_id
                svc.meta_client = client
                svc.meta_available = True
            else:
                # Fallback to default config client
                svc._init()
        except Exception:
            svc._init()
        return svc

    def list_campaigns(self, status_filter=None):
        if not self.meta_available:
            return []
        return self.meta_client.list_campaigns(status_filter=status_filter)

    def list_ad_sets(self, campaign_id=None):
        if not self.meta_available:
            return []
        return self.meta_client.list_ad_sets(campaign_id=campaign_id)

    def get_ad_set_insights(self, campaign_id, date_preset="last_7d"):
        if not self.meta_available:
            return []
        import requests
        url = f"https://graph.facebook.com/v21.0/{campaign_id}/insights"
        params = {
            "fields": "adset_name,adset_id,spend,impressions,clicks,ctr,actions,cost_per_action_type",
            "date_preset": date_preset,
            "level": "adset",
        }
        headers = {"Authorization": f"Bearer {self.meta_client.access_token}"}
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def update_campaign_status(self, campaign_id, status):
        if not self.meta_available:
            return {"error": "Meta client not available"}
        return self.meta_client.update_campaign_status(campaign_id, status)

    def update_ad_set_status(self, ad_set_id, status):
        if not self.meta_available:
            return {"error": "Meta client not available"}
        return self.meta_client.update_ad_set_status(ad_set_id, status)

    def check_token(self):
        if not self.meta_available:
            return {"is_valid": False, "error": "Meta client not available"}
        try:
            return self.meta_client.check_token_validity()
        except Exception as e:
            return {"is_valid": False, "error": str(e)}
