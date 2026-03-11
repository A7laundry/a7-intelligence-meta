"""Budget Intelligence Service — Analyzes spend efficiency, detects waste and scaling opportunities.

Rule-based engine that classifies campaign spend as efficient, waste, or neutral,
detects anomalies, monitors pacing, and computes a budget efficiency score.

TODO: Add automated budget reallocation execution (Phase 3+)
TODO: Add campaign auto-pause for critical waste (Phase 3+)
TODO: Add AI narrative layer for budget explanations (Phase 3+)
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import get_connection


class BudgetIntelligenceService:
    """Analyzes budget allocation efficiency and detects optimization opportunities."""

    # ── Thresholds ──
    WASTE_SPEND_MIN = 20.0          # Min spend to flag as waste
    CPA_WASTE_MULTIPLIER = 2.0      # CPA > Nx account avg = waste
    CTR_FLOOR = 0.3                 # CTR below this is extremely low
    SCALE_MIN_CONVERSIONS = 2       # Min conversions to suggest scaling
    SCALE_MAX_CPA_RATIO = 1.0       # CPA must be <= account avg to scale
    PACING_OVER_THRESHOLD = 1.5     # 150% of expected = overspending
    PACING_UNDER_THRESHOLD = 0.5    # 50% of expected = underspending
    ANOMALY_SPEND_SPIKE = 1.5       # 150% of daily average = spike
    ANOMALY_CONV_DROP = 0.5         # 50% drop in conversions = anomaly

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

    def analyze_budget_allocation(self, days=7, platform=None):
        """Classify spend across campaigns as efficient, waste, or neutral."""
        dashboard = self._get_dashboard_data(days)
        campaigns = self._get_campaigns(dashboard, platform)

        total_spend = sum(c.get("spend", 0) for c in campaigns)
        total_conv = sum(c.get("conversions", 0) for c in campaigns)
        avg_cpa = total_spend / total_conv if total_conv > 0 else 0

        efficient_spend = 0.0
        waste_spend = 0.0
        neutral_spend = 0.0
        efficient_campaigns = []
        waste_campaigns = []
        neutral_campaigns = []

        for c in campaigns:
            spend = c.get("spend", 0)
            conv = c.get("conversions", 0)
            cpa = c.get("cpa", 0)
            ctr = c.get("ctr", 0)
            name = c.get("name", "Unknown")
            status = (c.get("status", "") or "").upper()

            if status not in ("ACTIVE", "ENABLED"):
                continue

            if spend < 5:
                neutral_spend += spend
                neutral_campaigns.append({"name": name, "spend": spend, "reason": "Insufficient data"})
            elif conv > 0 and (avg_cpa == 0 or cpa <= avg_cpa):
                efficient_spend += spend
                efficient_campaigns.append({
                    "name": name, "spend": round(spend, 2),
                    "conversions": conv, "cpa": round(cpa, 2),
                    "reason": f"Converting at ${cpa:.2f} CPA (at or below average)"
                })
            elif spend >= self.WASTE_SPEND_MIN and conv == 0:
                waste_spend += spend
                waste_campaigns.append({
                    "name": name, "spend": round(spend, 2),
                    "reason": f"${spend:.2f} spent with zero conversions"
                })
            elif conv > 0 and avg_cpa > 0 and cpa > avg_cpa * self.CPA_WASTE_MULTIPLIER:
                waste_spend += spend
                waste_campaigns.append({
                    "name": name, "spend": round(spend, 2),
                    "conversions": conv, "cpa": round(cpa, 2),
                    "reason": f"CPA ${cpa:.2f} is {cpa/avg_cpa:.1f}x the account average"
                })
            elif ctr < self.CTR_FLOOR and spend >= self.WASTE_SPEND_MIN:
                waste_spend += spend
                waste_campaigns.append({
                    "name": name, "spend": round(spend, 2),
                    "ctr": round(ctr, 2),
                    "reason": f"Extremely low CTR ({ctr:.2f}%) with ${spend:.2f} spent"
                })
            else:
                neutral_spend += spend
                neutral_campaigns.append({
                    "name": name, "spend": round(spend, 2),
                    "reason": "Performance within normal range"
                })

        return {
            "total_spend": round(total_spend, 2),
            "efficient_spend": round(efficient_spend, 2),
            "waste_spend": round(waste_spend, 2),
            "neutral_spend": round(neutral_spend, 2),
            "ratios": {
                "efficient_pct": round(efficient_spend / total_spend * 100, 1) if total_spend > 0 else 0,
                "waste_pct": round(waste_spend / total_spend * 100, 1) if total_spend > 0 else 0,
                "neutral_pct": round(neutral_spend / total_spend * 100, 1) if total_spend > 0 else 0,
            },
            "efficient_campaigns": efficient_campaigns,
            "waste_campaigns": waste_campaigns,
            "neutral_campaigns": neutral_campaigns,
            "account_avg_cpa": round(avg_cpa, 2),
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def detect_scaling_opportunities(self, days=7, platform=None):
        """Identify campaigns suitable for budget increase."""
        dashboard = self._get_dashboard_data(days)
        campaigns = self._get_campaigns(dashboard, platform)

        total_spend = sum(c.get("spend", 0) for c in campaigns)
        total_conv = sum(c.get("conversions", 0) for c in campaigns)
        avg_cpa = total_spend / total_conv if total_conv > 0 else 0

        opportunities = []
        for c in campaigns:
            name = c.get("name", "Unknown")
            spend = c.get("spend", 0)
            conv = c.get("conversions", 0)
            cpa = c.get("cpa", 0)
            ctr = c.get("ctr", 0)
            status = (c.get("status", "") or "").upper()

            if status not in ("ACTIVE", "ENABLED"):
                continue
            if conv < self.SCALE_MIN_CONVERSIONS:
                continue
            if avg_cpa > 0 and cpa > avg_cpa * self.SCALE_MAX_CPA_RATIO:
                continue

            # Determine suggested increase
            if cpa < avg_cpa * 0.5 and conv >= 5:
                increase_pct = 30
                confidence = "high"
            elif cpa < avg_cpa * 0.8:
                increase_pct = 20
                confidence = "medium"
            else:
                increase_pct = 10
                confidence = "low"

            opportunities.append({
                "campaign_name": name,
                "current_spend": round(spend, 2),
                "suggested_budget_increase_pct": increase_pct,
                "confidence": confidence,
                "reason": f"CPA ${cpa:.2f} is below account average ${avg_cpa:.2f} with {conv} conversions",
                "metrics": {
                    "spend": round(spend, 2),
                    "conversions": conv,
                    "cpa": round(cpa, 2),
                    "ctr": round(ctr, 2),
                    "account_avg_cpa": round(avg_cpa, 2),
                },
            })

        opportunities.sort(key=lambda x: x["metrics"]["cpa"])
        return opportunities

    def detect_budget_waste(self, days=7, platform=None):
        """Detect campaigns wasting budget."""
        allocation = self.analyze_budget_allocation(days, platform)
        return {
            "waste_spend": allocation["waste_spend"],
            "waste_pct": allocation["ratios"]["waste_pct"],
            "campaigns": allocation["waste_campaigns"],
            "total_spend": allocation["total_spend"],
        }

    def detect_spend_anomalies(self, days=7):
        """Detect abnormal spend patterns using historical data."""
        conn = get_connection()
        try:
            since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            long_since = (datetime.utcnow() - timedelta(days=days * 3)).strftime("%Y-%m-%d")

            # Current period daily data
            current = conn.execute(
                """SELECT date, SUM(spend) as spend, SUM(conversions) as conv,
                          SUM(clicks) as clicks
                   FROM daily_snapshots WHERE date >= ? GROUP BY date ORDER BY date""",
                (since,)
            ).fetchall()

            # Historical average (3x period for baseline)
            baseline = conn.execute(
                """SELECT AVG(daily_spend) as avg_spend, AVG(daily_conv) as avg_conv
                   FROM (
                     SELECT date, SUM(spend) as daily_spend, SUM(conversions) as daily_conv
                     FROM daily_snapshots WHERE date >= ? AND date < ?
                     GROUP BY date
                   )""",
                (long_since, since)
            ).fetchone()

            avg_spend = (baseline["avg_spend"] or 0) if baseline else 0
            avg_conv = (baseline["avg_conv"] or 0) if baseline else 0

            anomalies = []
            for row in current:
                row = dict(row)
                day_spend = row["spend"] or 0
                day_conv = row["conv"] or 0

                # Spend spike
                if avg_spend > 0 and day_spend > avg_spend * self.ANOMALY_SPEND_SPIKE:
                    anomalies.append({
                        "date": row["date"],
                        "type": "spend_spike",
                        "severity": "warning",
                        "message": f"Spend ${day_spend:.2f} is {day_spend/avg_spend:.1f}x the daily average (${avg_spend:.2f})",
                        "metrics": {"spend": day_spend, "avg_spend": round(avg_spend, 2)},
                    })

                # Conversion drop with spend maintained
                if avg_conv > 0 and day_conv < avg_conv * self.ANOMALY_CONV_DROP and day_spend >= avg_spend * 0.8:
                    anomalies.append({
                        "date": row["date"],
                        "type": "conversion_drop",
                        "severity": "warning",
                        "message": f"Only {day_conv} conversions (avg: {avg_conv:.0f}) while spend was maintained at ${day_spend:.2f}",
                        "metrics": {"conversions": day_conv, "avg_conv": round(avg_conv, 1), "spend": day_spend},
                    })

            return {"anomalies": anomalies, "baseline": {"avg_daily_spend": round(avg_spend, 2), "avg_daily_conv": round(avg_conv, 1)}}
        except Exception:
            return {"anomalies": [], "baseline": {}}
        finally:
            conn.close()

    def monitor_budget_pacing(self, days=1, platform=None):
        """Compare expected vs actual spend for pacing analysis."""
        dashboard = self._get_dashboard_data(days)
        campaigns = self._get_campaigns(dashboard, platform)

        results = []
        for c in campaigns:
            name = c.get("name", "Unknown")
            status = (c.get("status", "") or "").upper()
            if status not in ("ACTIVE", "ENABLED"):
                continue

            spend = c.get("spend", 0)
            daily_budget = c.get("daily_budget", 0)
            lifetime_budget = c.get("lifetime_budget", 0)

            # Use daily budget if available, otherwise estimate from spend
            expected = daily_budget / 100 if daily_budget else 0  # Meta returns in cents

            if expected <= 0:
                # Fallback: estimate from historical avg
                expected = self._estimate_daily_budget(name, spend, days)

            if expected <= 0:
                continue

            ratio = spend / expected if expected > 0 else 0

            if ratio >= self.PACING_OVER_THRESHOLD:
                status_label = "overspending"
            elif ratio <= self.PACING_UNDER_THRESHOLD:
                status_label = "underspending"
            else:
                status_label = "on_track"

            results.append({
                "campaign_name": name,
                "actual_spend": round(spend, 2),
                "expected_spend": round(expected, 2),
                "pacing_ratio": round(ratio, 2),
                "status": status_label,
            })

        return {"campaigns": results, "period_days": days}

    def compute_efficiency_score(self, days=7, platform=None):
        """
        Budget Efficiency Score (0-100).

        Components:
        - Efficient spend ratio (40%): % of spend going to converting campaigns
        - Conversion efficiency (25%): conversions per dollar vs benchmark
        - Waste ratio inverse (20%): lower waste = higher score
        - Pacing stability (15%): campaigns on track vs off track
        """
        allocation = self.analyze_budget_allocation(days, platform)
        pacing = self.monitor_budget_pacing(days=1, platform=platform)

        # Component 1: Efficient spend ratio (0-100, weight 40%)
        eff_pct = allocation["ratios"]["efficient_pct"]
        eff_score = min(100, eff_pct * 1.25)  # 80% efficient = 100 score

        # Component 2: Conversion efficiency (0-100, weight 25%)
        total_spend = allocation["total_spend"]
        total_conv = sum(c.get("conversions", 0) for c in allocation["efficient_campaigns"])
        if total_spend > 0 and total_conv > 0:
            conv_per_dollar = total_conv / total_spend
            conv_score = min(100, conv_per_dollar * 2000)  # 0.05 conv/$ = 100
        elif total_spend == 0:
            conv_score = 50  # neutral
        else:
            conv_score = 0

        # Component 3: Waste ratio inverse (0-100, weight 20%)
        waste_pct = allocation["ratios"]["waste_pct"]
        waste_inv_score = max(0, 100 - waste_pct * 2.5)  # 40% waste = 0 score

        # Component 4: Pacing stability (0-100, weight 15%)
        pacing_campaigns = pacing.get("campaigns", [])
        if pacing_campaigns:
            on_track = sum(1 for p in pacing_campaigns if p["status"] == "on_track")
            pacing_score = (on_track / len(pacing_campaigns)) * 100
        else:
            pacing_score = 50  # neutral

        score = round(
            eff_score * 0.40 +
            conv_score * 0.25 +
            waste_inv_score * 0.20 +
            pacing_score * 0.15
        )
        score = max(0, min(100, score))

        return {
            "score": score,
            "components": {
                "efficient_spend_ratio": round(eff_score),
                "conversion_efficiency": round(conv_score),
                "waste_ratio_inverse": round(waste_inv_score),
                "pacing_stability": round(pacing_score),
            },
            "allocation": allocation["ratios"],
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    def _get_dashboard_data(self, days):
        if not self.dashboard_service:
            return {"summary": {"total": {}}, "campaigns": {"meta": [], "google": []}, "comparison": {}}
        range_key = "today" if days <= 1 else ("7d" if days <= 7 else "30d")
        try:
            return self.dashboard_service.get_dashboard_data(range_key)
        except Exception:
            return {"summary": {"total": {}}, "campaigns": {"meta": [], "google": []}, "comparison": {}}

    def _get_campaigns(self, dashboard, platform=None):
        campaigns = dashboard.get("campaigns", {})
        result = []
        if platform != "google":
            result.extend(campaigns.get("meta", []))
        if platform != "meta":
            result.extend(campaigns.get("google", []))
        return result

    def _estimate_daily_budget(self, name, current_spend, days):
        """Estimate daily budget from historical average spend."""
        if days > 0 and current_spend > 0:
            return current_spend / max(days, 1)
        return 0
