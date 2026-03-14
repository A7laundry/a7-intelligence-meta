"""Dashboard Service — Builds dashboard data from DB + live API with multi-account support."""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path for importing existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.snapshot_service import SnapshotService
from app.services.account_service import AccountService
from app.services.cache import dashboard_cache


_warned_once: set = set()  # Track per-process warnings; avoids repeated log spam

RANGES = {
    "today": {"meta_preset": "today", "google_range": "today", "days": 1},
    "7d": {"meta_preset": "last_7d", "google_range": "last_7d", "days": 7},
    "30d": {"meta_preset": "last_30d", "google_range": "last_30d", "days": 30},
}


class DashboardService:
    """Orchestrates dashboard data from live APIs + persisted snapshots."""

    def __init__(self):
        self.meta_client = None
        self.google_client = None
        self.meta_available = False
        self.google_available = False
        self._init_clients()

    def _init_clients(self):
        """Initialize API clients (reuses existing modules)."""
        # Try config-based Meta init first
        try:
            from config_default import META_CONFIG
            if META_CONFIG.get("access_token") and META_CONFIG["access_token"] not in ("", "SEU_ACCESS_TOKEN_LONGO_PRAZO"):
                from meta_client import MetaAdsClient
                self.meta_client = MetaAdsClient()
                self.meta_available = True
        except Exception:
            pass

        # Fallback: if no config token but DB accounts exist, mark meta as available
        if not self.meta_available:
            try:
                accounts = AccountService.get_all()
                meta_accounts = [a for a in accounts if a.get("platform") == "meta" and a.get("access_token")]
                if meta_accounts:
                    self.meta_available = True
                    # Don't set self.meta_client here — it will be created per-account in _get_meta_client_for_account
            except Exception:
                pass

        try:
            from config_default import GOOGLE_ADS_CONFIG
            if GOOGLE_ADS_CONFIG.get("developer_token") and GOOGLE_ADS_CONFIG["developer_token"] not in ("", "SEU_DEVELOPER_TOKEN"):
                try:
                    from app.services.google_ads_client import GoogleAdsApiClient
                except ImportError:
                    if "google_ads" not in _warned_once:
                        import logging as _logging
                        _logging.getLogger(__name__).warning(
                            "google_ads_client not available — Google Ads integration disabled"
                        )
                        _warned_once.add("google_ads")
                    GoogleAdsApiClient = None
                if GoogleAdsApiClient is not None:
                    self.google_client = GoogleAdsApiClient()
                    # Use wrapper's own availability check — init may succeed even if
                    # credentials are invalid; .available reflects the true state.
                    self.google_available = self.google_client.available
        except Exception:
            pass

    def _get_meta_client_for_account(self, account_id: int):
        """Return a Meta client configured for the given account_id, using the DB token."""
        if not self.meta_available:
            return None
        try:
            from meta_client import MetaAdsClient

            # Get the full account record from DB (already decrypted by AccountService)
            account = AccountService.get_by_id(account_id)
            if not account:
                return self.meta_client  # fallback to config client

            access_token = account.get("access_token")
            external_id = account.get("external_account_id")

            # Create client: use account token if available, else use default token
            # Always override ad_account_id so the correct account is queried
            client = MetaAdsClient(access_token=access_token) if access_token else MetaAdsClient()
            if external_id and hasattr(client, "ad_account_id"):
                client.ad_account_id = external_id

            return client
        except Exception:
            return self.meta_client

    def fetch_and_store(self, range_key: str = "today", account_id: int = None) -> dict:
        """Fetch live data, store snapshots, return dashboard payload."""
        if account_id is None:
            account_id = AccountService.resolve_account_id(None)
        cfg = RANGES.get(range_key, RANGES["7d"])
        today = datetime.utcnow().strftime("%Y-%m-%d")

        meta_data = self._fetch_meta(cfg["meta_preset"], account_id=account_id)
        google_data = self._fetch_google(cfg["google_range"])

        # Store snapshots (only for today's actual data)
        if meta_data and range_key == "today":
            SnapshotService.save_daily_snapshot(today, "meta", meta_data["summary"], account_id=account_id)
            for c in meta_data.get("campaigns", []):
                SnapshotService.save_campaign_snapshot(today, "meta", c, account_id=account_id)

        if google_data and range_key == "today":
            SnapshotService.save_daily_snapshot(today, "google", google_data["summary"], account_id=account_id)
            for c in google_data.get("campaigns", []):
                SnapshotService.save_campaign_snapshot(today, "google", c, account_id=account_id)

        return self._build_payload(meta_data, google_data, range_key, cfg, account_id=account_id)

    def get_dashboard_data(self, range_key: str = "7d", account_id: int = None) -> dict:
        """Get dashboard data — tries live first, falls back to DB."""
        if account_id is None:
            account_id = AccountService.resolve_account_id(None)

        cache_key = f"dashboard_{account_id}_{range_key}"
        cached = dashboard_cache.get(cache_key)
        if cached is not None:
            return cached

        cfg = RANGES.get(range_key, RANGES["7d"])

        meta_data = self._fetch_meta(cfg["meta_preset"], account_id=account_id)
        google_data = self._fetch_google(cfg["google_range"])

        if meta_data is None and google_data is None:
            # Try database
            db_data = self._build_from_db(range_key, cfg["days"], account_id=account_id)
            if db_data:
                dashboard_cache.set(cache_key, db_data)
                return db_data
            # Fall back to demo
            from dashboard_fetcher import DashboardFetcher
            return DashboardFetcher.generate_demo_data(range_key)

        result = self._build_payload(meta_data, google_data, range_key, cfg, account_id=account_id)
        dashboard_cache.set(cache_key, result)
        return result

    def _fetch_meta(self, date_preset: str, account_id: int = None):
        """Fetch Meta data using existing dashboard_fetcher logic."""
        if not self.meta_available:
            return None
        try:
            from dashboard_fetcher import DashboardFetcher
            fetcher = DashboardFetcher.__new__(DashboardFetcher)
            # Always use per-account client when account_id is provided
            if account_id:
                fetcher.meta_client = self._get_meta_client_for_account(account_id)
            else:
                fetcher.meta_client = self.meta_client
            fetcher.meta_available = fetcher.meta_client is not None
            fetcher.google_client = None
            fetcher.google_available = False
            if not fetcher.meta_available:
                return None
            return fetcher.fetch_meta_data(date_preset)
        except Exception:
            return None

    def _fetch_google(self, date_range: str):
        """Fetch Google data using existing dashboard_fetcher logic."""
        if not self.google_available:
            return None
        try:
            from dashboard_fetcher import DashboardFetcher
            fetcher = DashboardFetcher.__new__(DashboardFetcher)
            fetcher.meta_client = None
            fetcher.meta_available = False
            fetcher.google_client = self.google_client
            fetcher.google_available = True
            return fetcher.fetch_google_data(date_range)
        except Exception:
            return None

    def _build_payload(self, meta_data, google_data, range_key, cfg, account_id=None):
        """Build the unified dashboard payload."""
        empty = {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0,
                 "cpc": 0, "conversions": 0, "cpa": 0, "roas": 0}

        meta_summary = meta_data["summary"] if meta_data else empty.copy()
        google_summary = google_data["summary"] if google_data else empty.copy()

        total_spend = meta_summary["spend"] + google_summary["spend"]
        total_impressions = meta_summary["impressions"] + google_summary["impressions"]
        total_clicks = meta_summary["clicks"] + google_summary["clicks"]
        total_conversions = meta_summary["conversions"] + google_summary["conversions"]
        total_conversion_value = (
            meta_summary.get("conversion_value", 0) + google_summary.get("conversion_value", 0)
        )

        total_summary = {
            "spend": round(total_spend, 2),
            "impressions": total_impressions,
            "clicks": total_clicks,
            "ctr": round((total_clicks / total_impressions * 100) if total_impressions > 0 else 0, 2),
            "conversions": total_conversions,
            "conversion_value": round(total_conversion_value, 2),
            "cpa": round(total_spend / total_conversions, 2) if total_conversions > 0 else 0,
            "roas": round(total_conversion_value / total_spend, 2) if total_spend > 0 else 0,
        }

        # Period comparison from DB (account-scoped)
        comparison = SnapshotService.get_period_comparison(cfg["days"], account_id=account_id)

        # Campaign stats for hero KPIs
        all_camps = (
            (meta_data.get("campaigns", []) if meta_data else []) +
            (google_data.get("campaigns", []) if google_data else [])
        )
        active_count = sum(1 for c in all_camps if c.get("status") == "ACTIVE")
        top_camp = max(all_camps, key=lambda c: c.get("spend", 0), default=None)
        top_camp_name = top_camp.get("name", "—") if top_camp else "—"
        worst_camp = max(
            [c for c in all_camps if c.get("conversions", 0) > 0],
            key=lambda c: c.get("cpa", 0),
            default=None,
        )
        worst_camp_name = worst_camp.get("name", "—") if worst_camp else "—"

        return {
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_range": range_key,
            "demo": False,
            "account_id": account_id,
            "partial": (meta_data is None) or (google_data is None),
            "summary": {
                "meta": meta_summary,
                "google": google_summary,
                "total": total_summary,
            },
            "campaign_stats": {
                "total": len(all_camps),
                "active": active_count,
                "top_campaign": top_camp_name,
                "worst_campaign": worst_camp_name,
            },
            "campaigns": {
                "meta": meta_data.get("campaigns", []) if meta_data else [],
                "google": google_data.get("campaigns", []) if google_data else [],
            },
            "daily_trend": self._fetch_daily_trend(meta_data, google_data, cfg, account_id=account_id),
            "comparison": comparison,
            "platforms": {
                "meta": self.meta_available,
                "google": self.google_available,
            },
        }

    def _fetch_daily_trend(self, meta_data, google_data, cfg, account_id=None):
        """Build daily trend from live APIs."""
        meta_daily = {}
        google_daily = {}

        # Use per-account client when available, otherwise fall back to default
        effective_meta_client = None
        if self.meta_available:
            if account_id:
                effective_meta_client = self._get_meta_client_for_account(account_id)
            if effective_meta_client is None:
                effective_meta_client = self.meta_client

        if effective_meta_client:
            try:
                for row in effective_meta_client.get_daily_insights(date_preset=cfg["meta_preset"]):
                    date_start = row.get("date_start", "")
                    conversions = 0
                    for action in row.get("actions", []):
                        if action.get("action_type") in ("lead", "onsite_conversion.messaging_conversation_started_7d"):
                            conversions += int(action.get("value", 0))
                    meta_daily[date_start] = {"spend": float(row.get("spend", 0)), "conversions": conversions}
            except Exception:
                pass

        if self.google_available and self.google_client:
            try:
                for row in self.google_client.get_daily_metrics(date_range=cfg["google_range"]):
                    google_daily[row["date"]] = row
            except Exception:
                pass

        # Build complete date range — fill missing dates with zeros so charts
        # always render a full window (30 bars for 30d, not just days with spend)
        days = cfg.get("days", 7)
        end = datetime.utcnow().date()
        start = end - timedelta(days=days - 1)
        all_dates = [(start + timedelta(i)).strftime("%Y-%m-%d") for i in range(days)]

        return [
            {
                "date": d,
                "meta_spend": meta_daily.get(d, {}).get("spend", 0),
                "google_spend": google_daily.get(d, {}).get("spend", 0),
                "meta_conversions": meta_daily.get(d, {}).get("conversions", 0),
                "google_conversions": google_daily.get(d, {}).get("conversions", 0),
            }
            for d in all_dates
        ]

    def _build_from_db(self, range_key, days, account_id=None):
        """Build dashboard data from database snapshots (account-scoped)."""
        snapshots = SnapshotService.get_daily_snapshots(days=days, account_id=account_id)
        if not snapshots:
            return None

        # Build full date range so trend always has `days` entries (zeros for missing dates)
        end = datetime.utcnow().date()
        start = end - timedelta(days=days - 1)
        full_dates = [(start + timedelta(i)).strftime("%Y-%m-%d") for i in range(days)]
        snap_by_date_plat = {(s["date"], s["platform"]): s for s in snapshots}

        meta_rows = [s for s in snapshots if s["platform"] == "meta"]
        google_rows = [s for s in snapshots if s["platform"] == "google"]

        def aggregate(rows):
            if not rows:
                return {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0,
                        "cpc": 0, "conversions": 0, "conversion_value": 0, "cpa": 0, "roas": 0}
            spend = sum(r["spend"] for r in rows)
            impressions = sum(r["impressions"] for r in rows)
            clicks = sum(r["clicks"] for r in rows)
            conversions = sum(r["conversions"] for r in rows)
            conversion_value = sum(r.get("conversion_value", 0) for r in rows)
            return {
                "spend": round(spend, 2),
                "impressions": impressions,
                "clicks": clicks,
                "ctr": round((clicks / impressions * 100) if impressions > 0 else 0, 2),
                "cpc": round(spend / clicks, 2) if clicks > 0 else 0,
                "conversions": conversions,
                "conversion_value": round(conversion_value, 2),
                "cpa": round(spend / conversions, 2) if conversions > 0 else 0,
                "roas": round(conversion_value / spend, 2) if spend > 0 else 0,
            }

        meta_summary = aggregate(meta_rows)
        google_summary = aggregate(google_rows)
        total_summary = aggregate(meta_rows + google_rows)
        campaigns = SnapshotService.get_all_campaigns_latest(account_id=account_id)

        return {
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_range": range_key,
            "demo": False,
            "account_id": account_id,
            "partial": False,
            "source": "database",
            "summary": {"meta": meta_summary, "google": google_summary, "total": total_summary},
            "campaigns": {
                "meta": [dict(c) for c in campaigns if c["platform"] == "meta"],
                "google": [dict(c) for c in campaigns if c["platform"] == "google"],
            },
            "daily_trend": [
                {
                    "date": d,
                    "meta_spend": snap_by_date_plat.get((d, "meta"), {}).get("spend", 0),
                    "google_spend": snap_by_date_plat.get((d, "google"), {}).get("spend", 0),
                    "meta_conversions": snap_by_date_plat.get((d, "meta"), {}).get("conversions", 0),
                    "google_conversions": snap_by_date_plat.get((d, "google"), {}).get("conversions", 0),
                }
                for d in full_dates
            ],
            "comparison": SnapshotService.get_period_comparison(
                RANGES.get(range_key, {}).get("days", 7), account_id=account_id
            ),
        }
