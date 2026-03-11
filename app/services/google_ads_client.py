"""Google Ads Client Wrapper — Graceful fallback when credentials are missing.

Wraps the existing google_client.py from project root, providing a safe interface
that returns empty results when Google Ads is not configured.

TODO: Add TikTok Ads integration using same pattern
TODO: Add LinkedIn Ads integration using same pattern
TODO: Add Amazon Ads integration using same pattern
"""

import sys
import os
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger(__name__)


class GoogleAdsClientWrapper:
    """Safe wrapper around GoogleAdsApiClient with graceful fallback."""

    def __init__(self):
        self.client = None
        self.available = False
        self._init_client()

    def _init_client(self):
        """Try to initialize Google Ads client; fail silently if not configured."""
        try:
            from config import GOOGLE_ADS_CONFIG
            token = GOOGLE_ADS_CONFIG.get("developer_token", "")
            if not token or token in ("", "SEU_DEVELOPER_TOKEN"):
                logger.info("Google Ads not configured — skipping")
                return
            customer_id = GOOGLE_ADS_CONFIG.get("customer_id", "")
            if not customer_id or customer_id == "SEU_CUSTOMER_ID":
                logger.info("Google Ads customer_id not set — skipping")
                return

            from google_client import GoogleAdsApiClient
            self.client = GoogleAdsApiClient()
            self.available = True
            logger.info("Google Ads client initialized successfully")
        except ImportError:
            logger.info("Google Ads library not installed — skipping")
        except Exception as e:
            logger.warning("Google Ads client init failed: %s", e)

    def fetch_campaigns(self, status_filter=None):
        """Fetch campaigns list. Returns [] if unavailable."""
        if not self.available:
            return []
        try:
            campaigns = self.client.list_campaigns(status_filter=status_filter)
            # Normalize to platform-tagged structure
            for c in campaigns:
                c["platform"] = "google"
            return campaigns
        except Exception as e:
            logger.warning("Google Ads fetch_campaigns failed: %s", e)
            return []

    def fetch_campaign_metrics(self, date_range="last_7d"):
        """Fetch per-campaign metrics. Returns [] if unavailable."""
        if not self.available:
            return []
        try:
            metrics = self.client.get_campaign_insights(date_range=date_range)
            for m in metrics:
                m["platform"] = "google"
            return metrics
        except Exception as e:
            logger.warning("Google Ads fetch_campaign_metrics failed: %s", e)
            return []

    def fetch_account_metrics(self, date_range="last_7d"):
        """Fetch account-level metrics. Returns empty dict if unavailable."""
        if not self.available:
            return {}
        try:
            metrics = self.client.get_account_insights(date_range=date_range)
            metrics["platform"] = "google"
            return metrics
        except Exception as e:
            logger.warning("Google Ads fetch_account_metrics failed: %s", e)
            return {}

    def fetch_daily_metrics(self, date_range="last_7d"):
        """Fetch daily metrics for trends. Returns [] if unavailable."""
        if not self.available:
            return []
        try:
            return self.client.get_daily_metrics(date_range=date_range)
        except Exception as e:
            logger.warning("Google Ads fetch_daily_metrics failed: %s", e)
            return []
