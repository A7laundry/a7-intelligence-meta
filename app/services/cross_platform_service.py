"""Cross-Platform Intelligence Service — Unified analysis across Meta + Google Ads.

Compares platform performance, detects efficiency gaps, identifies budget
reallocation opportunities, and generates cross-channel insights.

TODO: Add TikTok Ads platform support
TODO: Add LinkedIn Ads platform support
TODO: Add Amazon Ads platform support
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import get_connection


class CrossPlatformService:
    """Analyzes and compares performance across advertising platforms."""

    def __init__(self):
        self.dashboard_service = None
        self._init_services()

    def _init_services(self):
        try:
            from app.services.dashboard_service import DashboardService
            self.dashboard_service = DashboardService()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def get_platform_summary(self, days=7):
        """Get aggregated metrics per platform with share of spend."""
        data = self._get_dashboard_data(days)
        summaries = data.get("summary", {})

        meta = summaries.get("meta", {})
        google = summaries.get("google", {})
        total_spend = (meta.get("spend", 0) or 0) + (google.get("spend", 0) or 0)

        platforms = []
        for name, s in [("meta", meta), ("google", google)]:
            spend = s.get("spend", 0) or 0
            conv = s.get("conversions", 0) or 0
            platforms.append({
                "platform": name,
                "spend": round(spend, 2),
                "impressions": s.get("impressions", 0) or 0,
                "clicks": s.get("clicks", 0) or 0,
                "conversions": conv,
                "ctr": round(s.get("ctr", 0) or 0, 2),
                "avg_cpa": round(spend / conv, 2) if conv > 0 else 0,
                "share_of_spend": round(spend / total_spend * 100, 1) if total_spend > 0 else 0,
            })

        return {
            "platforms": platforms,
            "total_spend": round(total_spend, 2),
            "period_days": days,
            "platforms_active": sum(1 for p in platforms if p["spend"] > 0),
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def get_channel_efficiency(self, days=7):
        """Compute efficiency metrics per platform for comparison."""
        summary = self.get_platform_summary(days)
        platforms = summary["platforms"]

        # Compute efficiency score per platform
        results = []
        for p in platforms:
            spend = p["spend"]
            conv = p["conversions"]
            cpa = p["avg_cpa"]
            ctr = p["ctr"]

            # Simple efficiency score: lower CPA + higher CTR = better
            if spend == 0:
                eff_score = 0
            elif conv == 0:
                eff_score = max(0, min(30, ctr * 10))  # some credit for engagement
            else:
                cpa_score = max(0, min(50, 50 - cpa))  # lower CPA = higher score
                ctr_score = min(30, ctr * 10)
                conv_score = min(20, conv * 2)
                eff_score = round(max(0, min(100, cpa_score + ctr_score + conv_score)))

            results.append({
                "platform": p["platform"],
                "efficiency_score": eff_score,
                "spend": spend,
                "conversions": conv,
                "avg_cpa": cpa,
                "ctr": ctr,
                "share_of_spend": p["share_of_spend"],
            })

        # Determine best channel
        best = max(results, key=lambda r: r["efficiency_score"]) if results else None

        return {
            "platforms": results,
            "best_channel": best["platform"] if best and best["efficiency_score"] > 0 else None,
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def detect_channel_opportunities(self, days=7):
        """Detect cross-platform optimization opportunities."""
        summary = self.get_platform_summary(days)
        platforms = {p["platform"]: p for p in summary["platforms"]}
        opportunities = []

        meta = platforms.get("meta", {})
        google = platforms.get("google", {})

        meta_spend = meta.get("spend", 0)
        google_spend = google.get("spend", 0)
        meta_cpa = meta.get("avg_cpa", 0)
        google_cpa = google.get("avg_cpa", 0)
        meta_ctr = meta.get("ctr", 0)
        google_ctr = google.get("ctr", 0)
        meta_conv = meta.get("conversions", 0)
        google_conv = google.get("conversions", 0)

        # CPA comparison
        if meta_cpa > 0 and google_cpa > 0:
            if google_cpa < meta_cpa * 0.76:
                diff_pct = round((1 - google_cpa / meta_cpa) * 100)
                opportunities.append({
                    "type": "channel_efficiency",
                    "severity": "success",
                    "title": f"Google Ads CPA is {diff_pct}% lower than Meta",
                    "message": f"Google CPA: ${google_cpa:.2f} vs Meta CPA: ${meta_cpa:.2f}. "
                               f"Consider shifting experimental budget toward Google.",
                    "from_platform": "meta",
                    "to_platform": "google",
                    "confidence": "high" if google_conv >= 5 else "medium",
                })
            elif meta_cpa < google_cpa * 0.76:
                diff_pct = round((1 - meta_cpa / google_cpa) * 100)
                opportunities.append({
                    "type": "channel_efficiency",
                    "severity": "success",
                    "title": f"Meta CPA is {diff_pct}% lower than Google",
                    "message": f"Meta CPA: ${meta_cpa:.2f} vs Google CPA: ${google_cpa:.2f}. "
                               f"Consider shifting experimental budget toward Meta.",
                    "from_platform": "google",
                    "to_platform": "meta",
                    "confidence": "high" if meta_conv >= 5 else "medium",
                })

        # CTR comparison
        if meta_ctr > 0 and google_ctr > 0:
            if meta_ctr > google_ctr * 1.5:
                opportunities.append({
                    "type": "engagement_gap",
                    "severity": "info",
                    "title": "Meta shows higher engagement than Google",
                    "message": f"Meta CTR: {meta_ctr:.2f}% vs Google CTR: {google_ctr:.2f}%. "
                               f"Meta campaigns show better audience-creative fit.",
                    "from_platform": None,
                    "to_platform": "meta",
                    "confidence": "medium",
                })
            elif google_ctr > meta_ctr * 1.5:
                opportunities.append({
                    "type": "engagement_gap",
                    "severity": "info",
                    "title": "Google shows higher engagement than Meta",
                    "message": f"Google CTR: {google_ctr:.2f}% vs Meta CTR: {meta_ctr:.2f}%. "
                               f"Google campaigns show better audience-creative fit.",
                    "from_platform": None,
                    "to_platform": "google",
                    "confidence": "medium",
                })

        # Concentration risk
        total_spend = meta_spend + google_spend
        if total_spend > 0:
            meta_share = meta_spend / total_spend * 100
            google_share = google_spend / total_spend * 100

            if meta_share > 90 and google_spend > 0:
                opportunities.append({
                    "type": "concentration_risk",
                    "severity": "warning",
                    "title": "High spend concentration on Meta",
                    "message": f"{meta_share:.0f}% of budget on Meta. Diversifying across channels "
                               f"reduces platform dependency risk.",
                    "from_platform": "meta",
                    "to_platform": "google",
                    "confidence": "medium",
                })
            elif google_share > 90 and meta_spend > 0:
                opportunities.append({
                    "type": "concentration_risk",
                    "severity": "warning",
                    "title": "High spend concentration on Google",
                    "message": f"{google_share:.0f}% of budget on Google. Diversifying across channels "
                               f"reduces platform dependency risk.",
                    "from_platform": "google",
                    "to_platform": "meta",
                    "confidence": "medium",
                })

        return {
            "opportunities": opportunities,
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def get_spend_share(self, days=7):
        """Get platform budget distribution for chart visualization."""
        summary = self.get_platform_summary(days)
        platforms = summary["platforms"]

        return {
            "labels": [p["platform"].title() for p in platforms],
            "values": [p["spend"] for p in platforms],
            "percentages": [p["share_of_spend"] for p in platforms],
            "total_spend": summary["total_spend"],
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def evaluate_cross_platform_budget(self, days=7):
        """Evaluate budget allocation across channels and suggest reallocations."""
        summary = self.get_platform_summary(days)
        platforms = {p["platform"]: p for p in summary["platforms"]}
        efficiency = self.get_channel_efficiency(days)
        eff_map = {p["platform"]: p for p in efficiency["platforms"]}

        meta = platforms.get("meta", {})
        google = platforms.get("google", {})

        meta_spend = meta.get("spend", 0)
        google_spend = google.get("spend", 0)
        total_spend = meta_spend + google_spend

        meta_eff = eff_map.get("meta", {}).get("efficiency_score", 0)
        google_eff = eff_map.get("google", {}).get("efficiency_score", 0)

        result = {
            "total_spend": round(total_spend, 2),
            "meta_spend": round(meta_spend, 2),
            "google_spend": round(google_spend, 2),
            "meta_efficiency": meta_eff,
            "google_efficiency": google_eff,
            "budget_reallocation_opportunity": None,
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # Only suggest reallocation if both platforms are active and there's a clear gap
        if meta_spend > 0 and google_spend > 0 and total_spend > 50:
            eff_gap = abs(meta_eff - google_eff)
            if eff_gap >= 15:
                if meta_eff > google_eff:
                    from_p, to_p = "google", "meta"
                    from_spend = google_spend
                else:
                    from_p, to_p = "meta", "google"
                    from_spend = meta_spend

                # Suggest shift of 10-20% based on gap
                shift_pct = min(20, max(10, round(eff_gap * 0.5)))
                confidence = "high" if eff_gap >= 30 else "medium"

                result["budget_reallocation_opportunity"] = {
                    "from_platform": from_p,
                    "to_platform": to_p,
                    "suggested_shift_pct": shift_pct,
                    "suggested_amount": round(from_spend * shift_pct / 100, 2),
                    "reason": f"{to_p.title()} shows {eff_gap:.0f} points higher efficiency score",
                    "confidence": confidence,
                }

        return result

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    def _get_dashboard_data(self, days):
        if not self.dashboard_service:
            return {
                "summary": {
                    "meta": {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0},
                    "google": {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0},
                    "total": {},
                },
                "campaigns": {"meta": [], "google": []},
            }
        range_key = "today" if days <= 1 else ("7d" if days <= 7 else "30d")
        try:
            return self.dashboard_service.get_dashboard_data(range_key)
        except Exception:
            return {
                "summary": {
                    "meta": {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0},
                    "google": {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0},
                    "total": {},
                },
                "campaigns": {"meta": [], "google": []},
            }
