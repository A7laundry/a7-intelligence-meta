"""
A7 Laundry - Dashboard Data Fetcher
Pulls Meta Ads + Google Ads data and writes unified JSON for the dashboard.

Usage:
    python3 dashboard_fetcher.py              # All ranges (today, 7d, 30d)
    python3 dashboard_fetcher.py --demo       # Demo data only
    python3 dashboard_fetcher.py --range 7d   # Specific range
    python3 dashboard_fetcher.py --serve      # Generate data then start server
    python3 dashboard_fetcher.py --embed      # Embed JSON data into index.html
"""

import json
import os
import re
import sys
import argparse
import random
from datetime import datetime, timedelta


DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")

RANGES = {
    "today": {"meta_preset": "today", "google_range": "today", "days": 1},
    "7d":    {"meta_preset": "last_7d", "google_range": "last_7d", "days": 7},
    "30d":   {"meta_preset": "last_30d", "google_range": "last_30d", "days": 30},
}


class DashboardFetcher:

    def __init__(self):
        self.meta_client = None
        self.google_client = None
        self.meta_available = False
        self.google_available = False
        self._init_clients()

    def _init_clients(self):
        """Try to initialize API clients; flag availability."""
        try:
            from config import META_CONFIG
            if META_CONFIG.get("access_token") and META_CONFIG["access_token"] != "SEU_ACCESS_TOKEN_LONGO_PRAZO":
                from meta_client import MetaAdsClient
                self.meta_client = MetaAdsClient()
                self.meta_available = True
                print("✅ Meta Ads client ready")
            else:
                print("⚠️  Meta Ads: credentials not configured")
        except Exception as e:
            print(f"⚠️  Meta Ads client unavailable: {e}")

        try:
            from config import GOOGLE_ADS_CONFIG
            if GOOGLE_ADS_CONFIG.get("developer_token") and GOOGLE_ADS_CONFIG["developer_token"] not in ("", "SEU_DEVELOPER_TOKEN"):
                from google_client import GoogleAdsApiClient
                self.google_client = GoogleAdsApiClient()
                self.google_available = True
                print("✅ Google Ads client ready")
            else:
                print("⚠️  Google Ads: credentials not configured")
        except Exception as e:
            print(f"⚠️  Google Ads client unavailable: {e}")

    # ------------------------------------------------------------------
    # Meta data fetcher
    # ------------------------------------------------------------------
    def fetch_meta_data(self, date_preset: str) -> dict:
        """Fetch Meta Ads account + campaign insights."""
        if not self.meta_available:
            return None

        try:
            account_data = self.meta_client.get_account_insights(date_preset=date_preset)
            account = account_data[0] if account_data else {}

            spend = float(account.get("spend", 0))
            impressions = int(account.get("impressions", 0))
            clicks = int(account.get("clicks", 0))
            ctr = float(account.get("ctr", 0))
            cpc = float(account.get("cpc", 0))

            # Extract conversions and conversions_value from actions
            conversions = 0
            conversions_value = 0
            for action in account.get("actions", []):
                atype = action.get("action_type", "")
                if atype in ("lead", "onsite_conversion.messaging_conversation_started_7d"):
                    conversions += int(action.get("value", 0))
                if atype == "offsite_conversion.fb_pixel_purchase":
                    conversions_value += float(action.get("value", 0))

            # Se não tem purchase value, estimar a partir de action_values
            if conversions_value == 0:
                for action in account.get("action_values", []):
                    atype = action.get("action_type", "")
                    if atype == "offsite_conversion.fb_pixel_purchase":
                        conversions_value += float(action.get("value", 0))

            cpa = round(spend / conversions, 2) if conversions > 0 else 0
            roas = round(conversions_value / spend, 2) if spend > 0 and conversions_value > 0 else 0

            summary = {
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": round(ctr, 2),
                "cpc": round(cpc, 2),
                "conversions": conversions,
                "cpa": cpa,
                "roas": roas,
            }

            # Campaign-level
            campaigns_raw = self.meta_client.list_campaigns(status_filter="ACTIVE")
            campaigns = []
            for c in campaigns_raw:
                try:
                    insights = self.meta_client.get_campaign_insights(c["id"], date_preset=date_preset)
                    if insights:
                        i = insights[0]
                        c_spend = float(i.get("spend", 0))
                        c_clicks = int(i.get("clicks", 0))
                        c_conversions = 0
                        c_conversions_value = 0
                        for action in i.get("actions", []):
                            atype = action.get("action_type", "")
                            if atype in ("lead", "onsite_conversion.messaging_conversation_started_7d"):
                                c_conversions += int(action.get("value", 0))
                            if atype == "offsite_conversion.fb_pixel_purchase":
                                c_conversions_value += float(action.get("value", 0))
                        for action in i.get("action_values", []):
                            if action.get("action_type") == "offsite_conversion.fb_pixel_purchase":
                                c_conversions_value += float(action.get("value", 0))
                        campaigns.append({
                            "id": c["id"],
                            "name": c.get("name", ""),
                            "status": c.get("status", "UNKNOWN"),
                            "spend": c_spend,
                            "clicks": c_clicks,
                            "ctr": round(float(i.get("ctr", 0)), 2),
                            "conversions": c_conversions,
                            "cpa": round(c_spend / c_conversions, 2) if c_conversions > 0 else 0,
                            "roas": round(c_conversions_value / c_spend, 2) if c_spend > 0 and c_conversions_value > 0 else 0,
                        })
                except Exception:
                    continue

            return {"summary": summary, "campaigns": campaigns}
        except Exception as e:
            print(f"❌ Error fetching Meta data: {e}")
            return None

    # ------------------------------------------------------------------
    # Google data fetcher
    # ------------------------------------------------------------------
    def fetch_google_data(self, date_range: str) -> dict:
        """Fetch Google Ads account + campaign insights."""
        if not self.google_available:
            return None

        try:
            summary = self.google_client.get_account_insights(date_range=date_range)
            campaigns = self.google_client.get_campaign_insights(date_range=date_range)
            return {"summary": summary, "campaigns": campaigns}
        except Exception as e:
            print(f"❌ Error fetching Google data: {e}")
            return None

    # ------------------------------------------------------------------
    # Daily trend
    # ------------------------------------------------------------------
    def fetch_daily_trend(self, date_range: str, days: int) -> list:
        """Fetch daily trend from both platforms."""
        meta_daily = {}
        google_daily = {}

        if self.meta_available:
            try:
                for row in self.meta_client.get_daily_insights(date_preset=date_range):
                    date_start = row.get("date_start", "")
                    conversions = 0
                    for action in row.get("actions", []):
                        if action.get("action_type") in ("lead", "onsite_conversion.messaging_conversation_started_7d"):
                            conversions += int(action.get("value", 0))
                    meta_daily[date_start] = {
                        "spend": float(row.get("spend", 0)),
                        "conversions": conversions,
                    }
            except Exception:
                pass

        if self.google_available:
            try:
                for row in self.google_client.get_daily_metrics(date_range=date_range):
                    google_daily[row["date"]] = row
            except Exception:
                pass

        all_dates = sorted(set(list(meta_daily.keys()) + list(google_daily.keys())))
        trend = []
        for d in all_dates:
            m = meta_daily.get(d, {})
            g = google_daily.get(d, {})
            trend.append({
                "date": d,
                "meta_spend": m.get("spend", 0),
                "google_spend": g.get("spend", 0),
                "meta_conversions": m.get("conversions", 0),
                "google_conversions": g.get("conversions", 0),
            })
        return trend

    # ------------------------------------------------------------------
    # Demo data generator
    # ------------------------------------------------------------------
    @staticmethod
    def generate_demo_data(range_key: str) -> dict:
        """Generate realistic demo data for testing the dashboard."""
        days = RANGES[range_key]["days"]
        now = datetime.utcnow()

        # Multipliers based on range
        mult = days

        def r(low, high):
            return round(random.uniform(low, high), 2)

        meta_spend = round(r(40, 60) * mult, 2)
        google_spend = round(r(50, 70) * mult, 2)
        meta_impressions = int(r(5000, 8000) * mult)
        google_impressions = int(r(4000, 7000) * mult)
        meta_clicks = int(meta_impressions * r(0.018, 0.028))
        google_clicks = int(google_impressions * r(0.022, 0.035))
        meta_conversions = max(1, int(meta_clicks * r(0.03, 0.06)))
        google_conversions = max(1, int(google_clicks * r(0.03, 0.06)))

        def make_summary(spend, impressions, clicks, conversions):
            ctr = round((clicks / impressions * 100) if impressions > 0 else 0, 2)
            cpc = round(spend / clicks, 2) if clicks > 0 else 0
            cpa = round(spend / conversions, 2) if conversions > 0 else 0
            roas = round((conversions * r(18, 35)) / spend, 2) if spend > 0 else 0
            return {
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "cpc": cpc,
                "conversions": conversions,
                "cpa": cpa,
                "roas": roas,
            }

        meta_summary = make_summary(meta_spend, meta_impressions, meta_clicks, meta_conversions)
        google_summary = make_summary(google_spend, google_impressions, google_clicks, google_conversions)

        total_spend = meta_spend + google_spend
        total_impressions = meta_impressions + google_impressions
        total_clicks = meta_clicks + google_clicks
        total_conversions = meta_conversions + google_conversions
        total_summary = make_summary(total_spend, total_impressions, total_clicks, total_conversions)

        # Demo campaigns
        meta_campaigns = [
            {"id": "120210001", "name": "A7 Orlando - Laundry Subscription", "status": "ACTIVE",
             "spend": round(meta_spend * 0.45, 2), "clicks": int(meta_clicks * 0.45),
             "ctr": r(1.8, 2.8), "conversions": max(1, int(meta_conversions * 0.5)),
             "cpa": 0, "roas": 0},
            {"id": "120210002", "name": "A7 Orlando - Carpet Cleaning", "status": "ACTIVE",
             "spend": round(meta_spend * 0.35, 2), "clicks": int(meta_clicks * 0.35),
             "ctr": r(1.5, 2.5), "conversions": max(1, int(meta_conversions * 0.3)),
             "cpa": 0, "roas": 0},
            {"id": "120210003", "name": "A7 Orlando - Retargeting", "status": "ACTIVE",
             "spend": round(meta_spend * 0.20, 2), "clicks": int(meta_clicks * 0.20),
             "ctr": r(2.0, 3.5), "conversions": max(1, int(meta_conversions * 0.2)),
             "cpa": 0, "roas": 0},
        ]
        for c in meta_campaigns:
            c["cpa"] = round(c["spend"] / c["conversions"], 2) if c["conversions"] > 0 else 0
            c["roas"] = round(r(2.0, 4.5), 2)

        google_campaigns = [
            {"id": "ggl_001", "name": "A7 Orlando - Search Laundry", "status": "ENABLED",
             "spend": round(google_spend * 0.40, 2), "clicks": int(google_clicks * 0.40),
             "ctr": r(2.5, 4.0), "conversions": max(1, int(google_conversions * 0.45)),
             "cpa": 0, "roas": 0},
            {"id": "ggl_002", "name": "A7 Orlando - Search Carpet", "status": "ENABLED",
             "spend": round(google_spend * 0.35, 2), "clicks": int(google_clicks * 0.35),
             "ctr": r(2.0, 3.5), "conversions": max(1, int(google_conversions * 0.35)),
             "cpa": 0, "roas": 0},
            {"id": "ggl_003", "name": "A7 Orlando - Display Retargeting", "status": "ENABLED",
             "spend": round(google_spend * 0.25, 2), "clicks": int(google_clicks * 0.25),
             "ctr": r(0.5, 1.5), "conversions": max(1, int(google_conversions * 0.20)),
             "cpa": 0, "roas": 0},
        ]
        for c in google_campaigns:
            c["cpa"] = round(c["spend"] / c["conversions"], 2) if c["conversions"] > 0 else 0
            c["roas"] = round(r(2.0, 5.0), 2)

        # Daily trend
        daily_trend = []
        for i in range(days):
            d = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            daily_trend.append({
                "date": d,
                "meta_spend": round(meta_spend / days * r(0.7, 1.3), 2),
                "google_spend": round(google_spend / days * r(0.7, 1.3), 2),
                "meta_conversions": max(0, int(meta_conversions / days * r(0.5, 1.5))),
                "google_conversions": max(0, int(google_conversions / days * r(0.5, 1.5))),
            })

        return {
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_range": f"last_{range_key}" if range_key != "today" else "today",
            "demo": True,
            "summary": {
                "meta": meta_summary,
                "google": google_summary,
                "total": total_summary,
            },
            "campaigns": {
                "meta": meta_campaigns,
                "google": google_campaigns,
            },
            "daily_trend": daily_trend,
        }

    # ------------------------------------------------------------------
    # Builder
    # ------------------------------------------------------------------
    def build_dashboard_data(self, range_key: str) -> dict:
        """Build unified dashboard data for a given range."""
        cfg = RANGES[range_key]
        now = datetime.utcnow()

        meta_data = self.fetch_meta_data(cfg["meta_preset"])
        google_data = self.fetch_google_data(cfg["google_range"])

        # If neither platform returned data, fall back to demo
        if meta_data is None and google_data is None:
            print(f"⚠️  No live data for {range_key}, using demo data")
            return self.generate_demo_data(range_key)

        # Build summaries
        meta_summary = meta_data["summary"] if meta_data else {
            "spend": 0, "impressions": 0, "clicks": 0, "ctr": 0,
            "cpc": 0, "conversions": 0, "cpa": 0, "roas": 0,
        }
        google_summary = google_data["summary"] if google_data else {
            "spend": 0, "impressions": 0, "clicks": 0, "ctr": 0,
            "cpc": 0, "conversions": 0, "cpa": 0, "roas": 0,
        }

        total_spend = meta_summary["spend"] + google_summary["spend"]
        total_impressions = meta_summary["impressions"] + google_summary["impressions"]
        total_clicks = meta_summary["clicks"] + google_summary["clicks"]
        total_conversions = meta_summary["conversions"] + google_summary["conversions"]
        total_summary = {
            "spend": round(total_spend, 2),
            "impressions": total_impressions,
            "clicks": total_clicks,
            "ctr": round((total_clicks / total_impressions * 100) if total_impressions > 0 else 0, 2),
            "conversions": total_conversions,
            "cpa": round(total_spend / total_conversions, 2) if total_conversions > 0 else 0,
            "roas": round(
                (meta_summary.get("roas", 0) * meta_summary["spend"] + google_summary.get("roas", 0) * google_summary["spend"]) / total_spend, 2
            ) if total_spend > 0 else 0,
        }

        # Campaigns
        meta_campaigns = meta_data.get("campaigns", []) if meta_data else []
        google_campaigns = google_data.get("campaigns", []) if google_data else []

        # Daily trend
        daily_trend = self.fetch_daily_trend(cfg["google_range"], cfg["days"])

        is_partial = (meta_data is None) or (google_data is None)

        return {
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_range": f"last_{range_key}" if range_key != "today" else "today",
            "demo": False,
            "partial": is_partial,
            "summary": {
                "meta": meta_summary,
                "google": google_summary,
                "total": total_summary,
            },
            "campaigns": {
                "meta": meta_campaigns,
                "google": google_campaigns,
            },
            "daily_trend": daily_trend,
        }

    # ------------------------------------------------------------------
    # Writer
    # ------------------------------------------------------------------
    def write_json(self, range_key: str, data: dict):
        """Write dashboard JSON to dashboard/ directory."""
        os.makedirs(DASHBOARD_DIR, exist_ok=True)
        filename = f"dashboard-data-{range_key}.json"
        filepath = os.path.join(DASHBOARD_DIR, filename)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        print(f"📄 Written: {filepath}")

    # ------------------------------------------------------------------
    # Embed data into index.html for file:// usage
    # ------------------------------------------------------------------
    @staticmethod
    def embed_data_into_html(all_data: dict):
        """Embed JSON data directly into index.html as a script tag.

        This allows the dashboard to work when opened as a file:// URL
        without needing an HTTP server.
        """
        index_path = os.path.join(DASHBOARD_DIR, "index.html")
        if not os.path.isfile(index_path):
            print(f"❌ index.html not found at {index_path}")
            return

        with open(index_path, "r") as f:
            html = f.read()

        # Build the inline data script
        data_json = json.dumps(all_data, separators=(",", ":"))
        script_tag = (
            '\n<!-- Embedded dashboard data for file:// usage (auto-generated) -->\n'
            '<script>window.__DASHBOARD_DATA__ = ' + data_json + ';</script>\n'
        )

        # Remove any previously embedded data block
        pattern = r'\n<!-- Embedded dashboard data for file:// usage \(auto-generated\) -->\n<script>window\.__DASHBOARD_DATA__\s*=\s*.*?;</script>\n'
        html = re.sub(pattern, '', html)

        # Insert before closing </body> tag
        html = html.replace('</body>', script_tag + '</body>')

        with open(index_path, "w") as f:
            f.write(html)

        print(f"📦 Embedded data into {index_path} (works with file:// URLs)")

    def run_all(self, demo: bool = False, range_filter: str = None, embed: bool = False):
        """Generate dashboard data for all (or one) range."""
        ranges_to_run = [range_filter] if range_filter else list(RANGES.keys())
        all_data = {}

        for rk in ranges_to_run:
            if rk not in RANGES:
                print(f"❌ Unknown range: {rk}")
                continue

            print(f"\n{'='*50}")
            print(f"📊 Generating dashboard data: {rk}")
            print(f"{'='*50}")

            if demo:
                data = self.generate_demo_data(rk)
            else:
                data = self.build_dashboard_data(rk)

            self.write_json(rk, data)
            all_data[rk] = data

        if embed:
            self.embed_data_into_html(all_data)

        print(f"\n✅ Done! Dashboard files in: {DASHBOARD_DIR}/")


def main():
    parser = argparse.ArgumentParser(description="A7 Dashboard Data Fetcher")
    parser.add_argument("--demo", action="store_true", help="Generate demo data only")
    parser.add_argument("--range", dest="range_key", choices=["today", "7d", "30d"],
                        help="Generate for specific range only")
    parser.add_argument("--serve", action="store_true",
                        help="Start HTTP server after generating data")
    parser.add_argument("--embed", action="store_true",
                        help="Embed JSON data into index.html for file:// usage")
    parser.add_argument("--port", type=int, default=8050,
                        help="Port for --serve (default: 8050)")
    args = parser.parse_args()

    fetcher = DashboardFetcher()
    fetcher.run_all(demo=args.demo, range_filter=args.range_key, embed=args.embed)

    if args.serve:
        from serve_dashboard import serve
        serve(port=args.port, open_browser=True)


if __name__ == "__main__":
    main()
