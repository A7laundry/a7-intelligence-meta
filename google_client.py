"""
A7 Laundry - Google Ads API Client
Mirrors meta_client.py structure for unified dashboard reporting.
"""

import time
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.api_core.exceptions import ServiceUnavailable, InternalServerError, DeadlineExceeded
from config_default import GOOGLE_ADS_CONFIG


# Map friendly range names to GAQL date range literals
DATE_RANGE_MAP = {
    "today": "TODAY",
    "yesterday": "YESTERDAY",
    "last_7d": "LAST_7_DAYS",
    "last_14d": "LAST_14_DAYS",
    "last_30d": "LAST_30_DAYS",
    "this_month": "THIS_MONTH",
    "last_month": "LAST_MONTH",
}


class GoogleAdsApiClient:
    """Client for Google Ads API reporting — mirrors MetaAdsClient interface."""

    def __init__(self):
        # Resolve login_customer_id: explicit env var preferred, falls back to customer_id
        # for non-MCC accounts where both values are the same.
        login_customer_id = (
            GOOGLE_ADS_CONFIG.get("login_customer_id")
            or GOOGLE_ADS_CONFIG.get("customer_id", "")
        ).replace("-", "")

        config_dict = {
            "developer_token": GOOGLE_ADS_CONFIG["developer_token"],
            "client_id": GOOGLE_ADS_CONFIG["client_id"],
            "client_secret": GOOGLE_ADS_CONFIG["client_secret"],
            "refresh_token": GOOGLE_ADS_CONFIG["refresh_token"],
            "use_proto_plus": False,
            "login_customer_id": login_customer_id,
        }

        self.client = GoogleAdsClient.load_from_dict(config_dict)
        self.customer_id = GOOGLE_ADS_CONFIG["customer_id"].replace("-", "")

    MAX_RETRIES = 3

    def _query(self, query: str) -> list:
        """Execute a GAQL query with retry for transient errors."""
        ga_service = self.client.get_service("GoogleAdsService")
        last_exception = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = ga_service.search(customer_id=self.customer_id, query=query)
                return list(response)
            except (ServiceUnavailable, InternalServerError, DeadlineExceeded) as e:
                if attempt < self.MAX_RETRIES:
                    delay = 2 ** attempt
                    print(f"⚠️ Google Ads erro transiente. Retry {attempt + 1}/{self.MAX_RETRIES} em {delay}s...")
                    time.sleep(delay)
                    last_exception = e
                    continue
                print(f"❌ Google Ads erro após {self.MAX_RETRIES} tentativas: {e}")
                raise
            except GoogleAdsException as ex:
                for error in ex.failure.errors:
                    print(f"❌ Google Ads API error: {error.message}")
                raise

        raise last_exception

    @staticmethod
    def _micros_to_dollars(micros) -> float:
        return round(micros / 1_000_000, 2)

    def list_campaigns(self, status_filter: str = None) -> list:
        """List campaigns with basic info."""
        where = ""
        if status_filter:
            where = f"AND campaign.status = '{status_filter}'"

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type
            FROM campaign
            WHERE campaign.status != 'REMOVED'
            {where}
            ORDER BY campaign.name
        """
        rows = self._query(query)
        return [
            {
                "id": str(row.campaign.id),
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "channel": row.campaign.advertising_channel_type.name,
            }
            for row in rows
        ]

    def get_account_insights(self, date_range: str = "last_7d") -> dict:
        """Get account-level aggregated metrics."""
        gaql_range = DATE_RANGE_MAP.get(date_range, "LAST_7_DAYS")

        query = f"""
            SELECT
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.ctr,
                metrics.average_cpc
            FROM customer
            WHERE segments.date DURING {gaql_range}
        """
        rows = self._query(query)
        if not rows:
            return {"impressions": 0, "clicks": 0, "spend": 0, "conversions": 0,
                    "conversions_value": 0, "ctr": 0, "cpc": 0}

        row = rows[0]
        m = row.metrics
        spend = self._micros_to_dollars(m.cost_micros)
        conversions = round(m.conversions, 2)
        return {
            "impressions": m.impressions,
            "clicks": m.clicks,
            "spend": spend,
            "conversions": conversions,
            "conversions_value": round(m.conversions_value, 2),
            "ctr": round(m.ctr * 100, 2),  # fraction → percentage
            "cpc": self._micros_to_dollars(m.average_cpc),
            "cpa": round(spend / conversions, 2) if conversions > 0 else 0,
            "roas": round(m.conversions_value / spend, 2) if spend > 0 else 0,
        }

    def get_campaign_insights(self, date_range: str = "last_7d") -> list:
        """Get per-campaign metrics."""
        gaql_range = DATE_RANGE_MAP.get(date_range, "LAST_7_DAYS")

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.ctr,
                metrics.average_cpc
            FROM campaign
            WHERE campaign.status != 'REMOVED'
                AND segments.date DURING {gaql_range}
            ORDER BY metrics.cost_micros DESC
        """
        rows = self._query(query)
        results = []
        for row in rows:
            m = row.metrics
            spend = self._micros_to_dollars(m.cost_micros)
            conversions = round(m.conversions, 2)
            results.append({
                "id": str(row.campaign.id),
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "impressions": m.impressions,
                "clicks": m.clicks,
                "spend": spend,
                "conversions": conversions,
                "ctr": round(m.ctr * 100, 2),
                "cpc": self._micros_to_dollars(m.average_cpc),
                "cpa": round(spend / conversions, 2) if conversions > 0 else 0,
                "roas": round(m.conversions_value / spend, 2) if spend > 0 else 0,
            })
        return results

    def get_daily_metrics(self, date_range: str = "last_7d") -> list:
        """Get daily spend and conversions for trend charts."""
        gaql_range = DATE_RANGE_MAP.get(date_range, "LAST_7_DAYS")

        query = f"""
            SELECT
                segments.date,
                metrics.cost_micros,
                metrics.conversions
            FROM customer
            WHERE segments.date DURING {gaql_range}
            ORDER BY segments.date ASC
        """
        rows = self._query(query)
        return [
            {
                "date": row.segments.date,
                "spend": self._micros_to_dollars(row.metrics.cost_micros),
                "conversions": round(row.metrics.conversions, 2),
            }
            for row in rows
        ]
