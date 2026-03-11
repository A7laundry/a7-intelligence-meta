"""Growth Score Service — Unified executive score (0-100) for account health and growth readiness.

Combines signals from AI Coach, Budget Intelligence, Creative Intelligence,
trend momentum, alert pressure, and channel balance into a single actionable score.

Score Components (weighted):
- Account Health (AI Coach):   25%  — conversion efficiency, trend, CTR
- Budget Efficiency:           25%  — efficient spend ratio, waste inverse
- Creative Health:             18%  — healthy creative ratio, top creative score
- Trend Momentum:              12%  — period-over-period improvement signals
- Channel Balance:             12%  — penalizes single-platform dependency
- Alert Cleanliness:            8%  — penalty for unresolved critical alerts

Labels:
- elite:   >= 85
- strong:  >= 70
- stable:  >= 50
- at_risk: >= 30
- weak:    < 30
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class GrowthScoreService:
    """Computes unified growth score from all intelligence modules."""

    def build_growth_score(self, days=7, platform=None, account_id=None):
        """Compute the unified growth score."""
        # Gather component scores
        account_health = self._get_account_health(days, platform, account_id=account_id)
        budget_efficiency = self._get_budget_efficiency(days, platform, account_id=account_id)
        creative_health = self._get_creative_health(days, account_id=account_id)
        trend_momentum = self._get_trend_momentum(days, account_id=account_id)
        channel_balance = self._get_channel_balance(days)
        alert_cleanliness = self._get_alert_cleanliness()

        # Weighted combination
        score = round(
            account_health["score"] * 0.25 +
            budget_efficiency["score"] * 0.25 +
            creative_health["score"] * 0.18 +
            trend_momentum["score"] * 0.12 +
            channel_balance["score"] * 0.12 +
            alert_cleanliness["score"] * 0.08
        )
        score = max(0, min(100, score))

        # Label
        if score >= 85:
            label = "elite"
        elif score >= 70:
            label = "strong"
        elif score >= 50:
            label = "stable"
        elif score >= 30:
            label = "at_risk"
        else:
            label = "weak"

        # Identify drivers
        components = {
            "account_health": account_health,
            "budget_efficiency": budget_efficiency,
            "creative_health": creative_health,
            "trend_momentum": trend_momentum,
            "channel_balance": channel_balance,
            "alert_cleanliness": alert_cleanliness,
        }
        top_positive = max(components.items(), key=lambda x: x[1]["score"])
        top_negative = min(components.items(), key=lambda x: x[1]["score"])

        # Summary
        summary = self._build_summary(score, label, top_positive, top_negative)

        return {
            "score": score,
            "label": label,
            "components": {k: v["score"] for k, v in components.items()},
            "component_details": components,
            "top_positive_driver": {
                "component": top_positive[0],
                "score": top_positive[1]["score"],
                "detail": top_positive[1].get("detail", ""),
            },
            "top_negative_driver": {
                "component": top_negative[0],
                "score": top_negative[1]["score"],
                "detail": top_negative[1].get("detail", ""),
            },
            "summary": summary,
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def _get_account_health(self, days, platform, account_id=None):
        """Get account health from AI Coach."""
        try:
            from app.services.ai_coach_service import AICoachService
            coach = AICoachService()
            health = coach.build_account_health_snapshot(days, platform, account_id=account_id)
            return {"score": health.get("score", 50), "detail": f"Health: {health.get('label', 'unknown')}"}
        except Exception:
            return {"score": 50, "detail": "No health data"}

    def _get_budget_efficiency(self, days, platform, account_id=None):
        """Get budget efficiency score."""
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            eff = bi.compute_efficiency_score(days, platform, account_id=account_id)
            return {"score": eff.get("score", 50), "detail": f"Efficiency: {eff.get('score', 0)}/100"}
        except Exception:
            return {"score": 50, "detail": "No budget data"}

    def _get_creative_health(self, days, account_id=None):
        """Compute creative health score."""
        try:
            from app.services.creative_service import CreativeService
            cs = CreativeService()
            creatives = cs.get_creatives(days=days, account_id=account_id)
            if not creatives:
                return {"score": 50, "detail": "No creative data"}

            healthy = sum(1 for c in creatives if c.get("fatigue_status") == "healthy")
            ratio = healthy / len(creatives)
            avg_score = sum(c.get("score", 0) for c in creatives) / len(creatives)

            # Blend ratio (60%) and average score (40%)
            score = round(ratio * 60 + (avg_score / 100) * 40)
            fatigued = len(creatives) - healthy
            detail = f"{healthy}/{len(creatives)} healthy" + (f", {fatigued} fatigued" if fatigued else "")
            return {"score": max(0, min(100, score)), "detail": detail}
        except Exception:
            return {"score": 50, "detail": "No creative data"}

    def _get_trend_momentum(self, days, account_id=None):
        """Compute trend momentum from period comparison."""
        try:
            from app.services.snapshot_service import SnapshotService
            comparison = SnapshotService.get_period_comparison(days, account_id=account_id)
            changes = comparison.get("changes", {})

            conv_change = changes.get("conversions", 0)
            spend_change = changes.get("spend", 0)
            click_change = changes.get("clicks", 0)

            # Start at 50 (neutral), adjust based on trends
            score = 50
            if conv_change > 20:
                score += 25
            elif conv_change > 5:
                score += 15
            elif conv_change < -20:
                score -= 25
            elif conv_change < -5:
                score -= 15

            # Efficiency signal: conversions up more than spend
            if conv_change > spend_change + 10:
                score += 10
            elif spend_change > conv_change + 15:
                score -= 10

            if click_change > 10:
                score += 5

            score = max(0, min(100, score))
            detail = f"Conv {conv_change:+.0f}%, Spend {spend_change:+.0f}%"
            return {"score": score, "detail": detail}
        except Exception:
            return {"score": 50, "detail": "No trend data"}

    def _get_channel_balance(self, days):
        """Score based on cross-platform spend diversification.

        100 = balanced (50/50 split), 0 = 100% on one platform.
        Single-platform accounts get 50 (neutral) — no penalty for
        not having Google if only using Meta.
        """
        try:
            from app.services.cross_platform_service import CrossPlatformService
            cp = CrossPlatformService()
            summary = cp.get_platform_summary(days)
            platforms = summary.get("platforms", [])

            active = [p for p in platforms if p.get("spend", 0) > 0]
            if len(active) <= 1:
                return {"score": 50, "detail": "Single platform active (neutral)"}

            shares = [p.get("share_of_spend", 0) for p in active]
            max_share = max(shares)

            # Perfect balance = 50% each = 100 score
            # 90/10 split = 20 score, 100/0 = 0
            if max_share <= 60:
                score = 100
            elif max_share <= 70:
                score = 80
            elif max_share <= 80:
                score = 60
            elif max_share <= 90:
                score = 40
            else:
                score = max(0, round(100 - max_share))

            detail = " / ".join(f"{p['platform'].title()}: {p['share_of_spend']:.0f}%" for p in active)
            return {"score": score, "detail": detail}
        except Exception:
            return {"score": 50, "detail": "No channel data"}

    def _get_alert_cleanliness(self):
        """Score based on unresolved critical alerts (fewer = better)."""
        try:
            from app.db.init_db import get_connection
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM alerts WHERE resolved = 0 AND severity = 'critical'"
                ).fetchone()
                critical_count = row["cnt"] if row else 0

                row2 = conn.execute(
                    "SELECT COUNT(*) as cnt FROM alerts WHERE resolved = 0 AND severity = 'warning'"
                ).fetchone()
                warning_count = row2["cnt"] if row2 else 0
            finally:
                conn.close()

            # 0 critical = 100, each critical = -20, each warning = -5
            score = max(0, 100 - (critical_count * 20) - (warning_count * 5))
            detail = f"{critical_count} critical, {warning_count} warnings"
            return {"score": score, "detail": detail}
        except Exception:
            return {"score": 80, "detail": "No alert data"}

    def _build_summary(self, score, label, top_positive, top_negative):
        """Build one-line executive summary."""
        label_text = label.replace("_", " ").title()
        pos_name = top_positive[0].replace("_", " ").title()
        neg_name = top_negative[0].replace("_", " ").title()

        if score >= 70:
            return f"Account is {label_text} ({score}/100). Strongest area: {pos_name}."
        elif score >= 50:
            return f"Account is {label_text} ({score}/100). Watch: {neg_name} ({top_negative[1]['score']}/100)."
        else:
            return f"Account needs attention ({score}/100). Priority: improve {neg_name} ({top_negative[1]['score']}/100)."
