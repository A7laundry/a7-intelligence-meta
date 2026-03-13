"""TikTok Ads API client — Marketing API v1.3."""
import os
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TIKTOK_API_BASE = "https://business-api.tiktok.com/open_api/v1.3"


class TikTokAdsClient:
    """Client for TikTok Marketing API."""

    def __init__(self, access_token=None, advertiser_id=None):
        self.access_token = access_token or os.environ.get("TIKTOK_ACCESS_TOKEN", "")
        self.advertiser_id = advertiser_id or os.environ.get("TIKTOK_ADVERTISER_ID", "")

    def _request(self, method, path, params=None, json=None):
        url = f"{TIKTOK_API_BASE}{path}"
        headers = {
            "Access-Token": self.access_token,
            "Content-Type": "application/json",
        }
        resp = requests.request(method, url, headers=headers, params=params, json=json, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"TikTok API error: {data.get('message', 'Unknown error')}")
        return data.get("data", {})

    def validate_token(self):
        """Validate access token by fetching advertiser info."""
        data = self._request("GET", "/oauth2/advertiser/get/", params={
            "advertiser_ids": f'["{self.advertiser_id}"]',
            "fields": '["name","status"]',
        })
        advertisers = data.get("list", [])
        return advertisers[0] if advertisers else None

    def get_account_insights(self, start_date, end_date):
        """Fetch account-level metrics for a date range."""
        data = self._request("GET", "/report/integrated/get/", params={
            "advertiser_id": self.advertiser_id,
            "report_type": "BASIC",
            "dimensions": '["stat_time_day"]',
            "metrics": '["spend","impressions","clicks","ctr","cpc","conversions","cost_per_conversion","real_time_conversion_rate"]',
            "start_date": start_date,
            "end_date": end_date,
            "page_size": 100,
        })
        rows = data.get("list", [])
        total = {
            "spend": 0.0, "impressions": 0, "clicks": 0,
            "conversions": 0, "ctr": 0.0, "cpc": 0.0, "cpa": 0.0,
        }
        daily = []
        for row in rows:
            metrics = row.get("metrics", {})
            dims = row.get("dimensions", {})
            spend = float(metrics.get("spend", 0))
            impressions = int(metrics.get("impressions", 0))
            clicks = int(metrics.get("clicks", 0))
            convs = int(metrics.get("conversions", 0))
            total["spend"] += spend
            total["impressions"] += impressions
            total["clicks"] += clicks
            total["conversions"] += convs
            daily.append({
                "date": dims.get("stat_time_day", "")[:10],
                "spend": spend, "impressions": impressions,
                "clicks": clicks, "conversions": convs,
            })

        total["ctr"] = round(total["clicks"] / total["impressions"] * 100, 2) if total["impressions"] > 0 else 0
        total["cpc"] = round(total["spend"] / total["clicks"], 2) if total["clicks"] > 0 else 0
        total["cpa"] = round(total["spend"] / total["conversions"], 2) if total["conversions"] > 0 else 0
        return {"summary": total, "daily": daily}

    def get_campaign_insights(self, start_date, end_date):
        """Fetch campaign-level metrics."""
        data = self._request("GET", "/report/integrated/get/", params={
            "advertiser_id": self.advertiser_id,
            "report_type": "BASIC",
            "dimensions": '["campaign_id","campaign_name"]',
            "metrics": '["spend","impressions","clicks","conversions","ctr","cpc"]',
            "start_date": start_date,
            "end_date": end_date,
            "page_size": 50,
        })
        campaigns = []
        for row in data.get("list", []):
            m = row.get("metrics", {})
            d = row.get("dimensions", {})
            campaigns.append({
                "campaign_id": d.get("campaign_id"),
                "campaign_name": d.get("campaign_name"),
                "spend": float(m.get("spend", 0)),
                "impressions": int(m.get("impressions", 0)),
                "clicks": int(m.get("clicks", 0)),
                "conversions": int(m.get("conversions", 0)),
                "ctr": float(m.get("ctr", 0)),
                "cpc": float(m.get("cpc", 0)),
            })
        return campaigns
