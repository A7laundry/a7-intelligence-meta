"""AI Campaign Coach Service — Rule-based insight engine for Meta Ads performance.

Analyzes campaign and creative performance data to produce actionable insights,
daily briefings, recommendations, and account health assessments.

The engine is deterministic (rule-based) by design. An optional LLM layer
(OpenAI / Anthropic) can enrich briefings with natural language narratives.
Set LLM_PROVIDER env var to "openai" or "anthropic" to enable; the rule-based
engine always runs first and serves as fallback if the LLM is unavailable.
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import get_connection


class AICoachService:
    """Rule-based AI Coach that transforms metrics into actionable insights."""

    # ── Thresholds (tunable) ──────────────────────────────────
    CPA_HIGH_THRESHOLD = 50.0       # CPA above this is concerning
    CPA_GOOD_THRESHOLD = 25.0       # CPA below this is strong
    CTR_LOW_THRESHOLD = 0.5         # CTR below this % is poor
    CTR_GOOD_THRESHOLD = 2.0        # CTR above this % is strong
    SPEND_WASTE_THRESHOLD = 30.0    # Spend with 0 conversions = waste alert
    SCALE_MIN_CONVERSIONS = 2       # Minimum conversions to recommend scaling
    FATIGUE_FREQ_THRESHOLD = 3.0    # Frequency above this signals fatigue

    def __init__(self):
        self.dashboard_service = None
        self.creative_service = None
        self._init_services()

    def _init_services(self):
        try:
            from app.services.dashboard_service import DashboardService
            self.dashboard_service = DashboardService()
        except Exception:
            pass
        try:
            from app.services.creative_service import CreativeService
            self.creative_service = CreativeService()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def generate_daily_briefing(self, days=7, platform=None, account_id=None):
        """Generate a structured daily briefing with headline, bullets, and highlights."""
        dashboard = self._get_dashboard_data(days, account_id=account_id)
        campaigns = self._get_all_campaigns(dashboard)
        creatives = self._get_creatives(days, account_id=account_id)
        comparison = dashboard.get("comparison", {})
        changes = comparison.get("changes", {})

        summary = dashboard.get("summary", {}).get("total", {})
        spend = summary.get("spend", 0)
        conversions = summary.get("conversions", 0)
        cpa = summary.get("cpa", 0)
        ctr = summary.get("ctr", 0)

        # Build headline
        headline = self._build_headline(spend, conversions, cpa, changes, days)

        # Summary bullets
        bullets = self._build_summary_bullets(summary, changes, campaigns, creatives, days)

        # Find top campaign and top creative
        top_campaign = self._find_top_campaign(campaigns)
        top_creative = self._find_top_creative(creatives)

        # Find top opportunity and risk
        recommendations = self.generate_recommendations(days, platform, account_id=account_id)
        top_opportunity = next((r for r in recommendations if r["severity"] == "success"), None)
        top_risk = next((r for r in recommendations if r["severity"] in ("critical", "warning")), None)

        # Health
        health = self.build_account_health_snapshot(days, platform, account_id=account_id)

        result = {
            "headline": headline,
            "summary_bullets": bullets,
            "top_opportunity": top_opportunity,
            "top_risk": top_risk,
            "top_campaign": top_campaign,
            "top_creative": top_creative,
            "health_label": health.get("label", "stable"),
            "health_score": health.get("score", 50),
            "period_days": days,
            "metrics": {
                "spend": spend,
                "conversions": conversions,
                "cpa": cpa,
                "ctr": ctr,
            },
            "changes": changes,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        # Optional: enhance with LLM narrative (always graceful fallback)
        try:
            from app.services.llm_service import is_available, complete
            if is_available():
                summary_data = {
                    "spend": spend,
                    "conversions": conversions,
                    "ctr": ctr,
                    "cpa": cpa,
                    "health_label": result["health_label"],
                    "health_score": result["health_score"],
                    "top_issues": [
                        r.get("title", "") for r in recommendations[:3]
                        if r.get("severity") in ("critical", "warning")
                    ],
                }
                narrative = complete(
                    system_prompt="You are an expert digital marketing analyst. Be concise, data-driven, and actionable. Max 2 sentences.",
                    user_prompt=f"Account performance summary: {summary_data}. Give a brief strategic narrative.",
                    max_tokens=150,
                )
                if narrative:
                    result["narrative"] = narrative
        except Exception:
            pass  # LLM is always optional

        return result

    def generate_recommendations(self, days=7, platform=None, account_id=None):
        """Generate prioritized recommendation cards from rule-based analysis."""
        recommendations = []
        seen_keys = set()  # deduplication

        # Analyze campaigns
        campaign_recs = self.analyze_campaigns(days, platform, account_id=account_id)
        for r in campaign_recs:
            key = f"{r['type']}:{r.get('entity_name', '')}"
            if key not in seen_keys:
                seen_keys.add(key)
                recommendations.append(r)

        # Analyze creatives
        creative_recs = self.analyze_creatives(days, platform, account_id=account_id)
        for r in creative_recs:
            key = f"{r['type']}:{r.get('entity_name', '')}"
            if key not in seen_keys:
                seen_keys.add(key)
                recommendations.append(r)

        # Account-level insights
        account_recs = self._analyze_account_level(days)
        for r in account_recs:
            key = f"{r['type']}:account"
            if key not in seen_keys:
                seen_keys.add(key)
                recommendations.append(r)

        # Cross-platform insights
        cross_recs = self._analyze_cross_platform(days)
        for r in cross_recs:
            key = f"{r['type']}:{r.get('entity_name', 'cross')}"
            if key not in seen_keys:
                seen_keys.add(key)
                recommendations.append(r)

        # Sort by severity priority: critical > warning > success > info
        severity_order = {"critical": 0, "warning": 1, "success": 2, "info": 3}
        recommendations.sort(key=lambda r: (severity_order.get(r["severity"], 4), -r.get("_impact", 0)))

        # Assign sequential IDs and clean up internal fields
        for i, r in enumerate(recommendations, 1):
            r["id"] = i
            r.pop("_impact", None)

        return recommendations

    def analyze_campaigns(self, days=7, platform=None, account_id=None):
        """Detect campaign-level patterns and generate recommendations."""
        dashboard = self._get_dashboard_data(days, account_id=account_id)
        campaigns = self._get_all_campaigns(dashboard, platform)
        if not campaigns:
            return []

        # Compute account averages for relative comparison
        total_spend = sum(c.get("spend", 0) for c in campaigns)
        total_conv = sum(c.get("conversions", 0) for c in campaigns)
        avg_cpa = total_spend / total_conv if total_conv > 0 else 0
        avg_ctr = sum(c.get("ctr", 0) for c in campaigns) / len(campaigns) if campaigns else 0

        recs = []
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        for c in campaigns:
            name = c.get("name", "Unknown")
            spend = c.get("spend", 0)
            conversions = c.get("conversions", 0)
            cpa = c.get("cpa", 0)
            ctr = c.get("ctr", 0)
            status = (c.get("status", "") or "").upper()

            if status not in ("ACTIVE", "ENABLED"):
                continue

            # ── Rule 1: Waste Alert — high spend, zero conversions ──
            if spend >= self.SPEND_WASTE_THRESHOLD and conversions == 0:
                recs.append(self._make_rec(
                    rec_type="waste_alert",
                    severity="critical",
                    title=f"{name} is spending without results",
                    message=f"This campaign has spent ${spend:.2f} over the last {days} days with zero conversions.",
                    recommendation="Consider pausing this campaign, revising targeting, or replacing creatives.",
                    entity_type="campaign",
                    entity_name=name,
                    metrics={"spend": spend, "conversions": 0, "ctr": ctr},
                    impact=spend,
                    created_at=now,
                ))

            # ── Rule 2: Very high CPA ──
            elif conversions > 0 and cpa > self.CPA_HIGH_THRESHOLD:
                recs.append(self._make_rec(
                    rec_type="high_cpa",
                    severity="warning",
                    title=f"{name} has high acquisition cost",
                    message=f"CPA is ${cpa:.2f} (account average: ${avg_cpa:.2f}). Efficiency is below target.",
                    recommendation="Review targeting, ad creative, or landing page to improve conversion rate.",
                    entity_type="campaign",
                    entity_name=name,
                    metrics={"spend": spend, "conversions": conversions, "cpa": cpa, "account_avg_cpa": round(avg_cpa, 2)},
                    impact=spend * 0.5,
                    created_at=now,
                ))

            # ── Rule 3: Scaling Opportunity — efficient + converting ──
            elif conversions >= self.SCALE_MIN_CONVERSIONS and cpa < avg_cpa * 0.8 and cpa <= self.CPA_GOOD_THRESHOLD:
                recs.append(self._make_rec(
                    rec_type="scaling_opportunity",
                    severity="success",
                    title=f"{name} is a top performer",
                    message=f"CPA ${cpa:.2f} is well below account average (${avg_cpa:.2f}) with {conversions} conversions.",
                    recommendation="Consider increasing budget by 20-30% to capture more volume at this efficiency.",
                    entity_type="campaign",
                    entity_name=name,
                    metrics={"spend": spend, "conversions": conversions, "cpa": cpa, "ctr": ctr},
                    impact=conversions * 10,
                    created_at=now,
                ))

            # ── Rule 4: Low CTR Warning ──
            elif ctr < self.CTR_LOW_THRESHOLD and spend > 10:
                recs.append(self._make_rec(
                    rec_type="low_ctr",
                    severity="warning",
                    title=f"{name} has low click-through rate",
                    message=f"CTR is {ctr:.2f}% which is below the {self.CTR_LOW_THRESHOLD}% threshold.",
                    recommendation="Test new ad copy, visuals, or audience targeting to improve engagement.",
                    entity_type="campaign",
                    entity_name=name,
                    metrics={"spend": spend, "ctr": ctr, "clicks": c.get("clicks", 0)},
                    impact=spend * 0.3,
                    created_at=now,
                ))

            # ── Rule 5: Strong performer (good CTR + conversions) ──
            elif ctr >= self.CTR_GOOD_THRESHOLD and conversions > 0:
                recs.append(self._make_rec(
                    rec_type="strong_performer",
                    severity="success",
                    title=f"{name} shows strong engagement",
                    message=f"CTR {ctr:.2f}% is excellent with {conversions} conversions at ${cpa:.2f} CPA.",
                    recommendation="This campaign is performing well. Monitor and protect its budget.",
                    entity_type="campaign",
                    entity_name=name,
                    metrics={"spend": spend, "conversions": conversions, "cpa": cpa, "ctr": ctr},
                    impact=conversions * 5,
                    created_at=now,
                ))

        return recs

    def analyze_creatives(self, days=7, platform=None, account_id=None):
        """Analyze creative performance and generate recommendations."""
        creatives = self._get_creatives(days, account_id=account_id)
        if not creatives:
            return []

        recs = []
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Sort by score to find top/bottom
        sorted_creatives = sorted(creatives, key=lambda c: c.get("score", 0), reverse=True)

        # ── Rule: Creative Winner ──
        if sorted_creatives:
            top = sorted_creatives[0]
            if top.get("score", 0) >= 50 and top.get("conversions", 0) > 0:
                recs.append(self._make_rec(
                    rec_type="creative_winner",
                    severity="success",
                    title=f"'{top['name']}' is your best creative",
                    message=f"Score {top['score']}/100 with {top['conversions']} conversions at {top.get('ctr', 0):.2f}% CTR.",
                    recommendation="Consider cloning this creative angle into new variations or expanding to new audiences.",
                    entity_type="creative",
                    entity_name=top["name"],
                    metrics={"score": top["score"], "conversions": top["conversions"],
                             "ctr": top.get("ctr", 0), "spend": top.get("spend", 0)},
                    impact=top["score"],
                    created_at=now,
                ))

        # ── Rule: Weak Creatives ──
        for c in sorted_creatives:
            if c.get("score", 0) < 20 and c.get("spend", 0) > 20:
                recs.append(self._make_rec(
                    rec_type="creative_weak",
                    severity="warning",
                    title=f"'{c['name']}' is underperforming",
                    message=f"Score {c['score']}/100 with ${c['spend']:.2f} spent. Low efficiency compared to other creatives.",
                    recommendation="Consider pausing this creative and reallocating budget to better performers.",
                    entity_type="creative",
                    entity_name=c["name"],
                    metrics={"score": c["score"], "spend": c.get("spend", 0),
                             "conversions": c.get("conversions", 0)},
                    impact=c.get("spend", 0),
                    created_at=now,
                ))

        # ── Rule: Creative Fatigue ──
        for c in creatives:
            fatigue = c.get("fatigue_status", "healthy")
            if fatigue in ("fatigued", "critical"):
                recs.append(self._make_rec(
                    rec_type="creative_fatigue",
                    severity="critical" if fatigue == "critical" else "warning",
                    title=f"'{c['name']}' shows fatigue signals",
                    message=f"Fatigue status: {fatigue}. Frequency: {c.get('frequency', 0):.1f}. CTR may be declining.",
                    recommendation="Refresh this creative with new copy or visuals to prevent further efficiency decay.",
                    entity_type="creative",
                    entity_name=c["name"],
                    metrics={"fatigue_status": fatigue, "frequency": c.get("frequency", 0),
                             "ctr": c.get("ctr", 0), "score": c.get("score", 0)},
                    impact=c.get("spend", 0) * 1.5,
                    created_at=now,
                ))
            elif fatigue == "warning":
                recs.append(self._make_rec(
                    rec_type="creative_fatigue_warning",
                    severity="info",
                    title=f"'{c['name']}' is approaching fatigue",
                    message=f"Frequency is {c.get('frequency', 0):.1f}. Monitor CTR trend closely.",
                    recommendation="Prepare replacement creatives. If CTR drops further, rotate immediately.",
                    entity_type="creative",
                    entity_name=c["name"],
                    metrics={"fatigue_status": fatigue, "frequency": c.get("frequency", 0)},
                    impact=c.get("spend", 0) * 0.5,
                    created_at=now,
                ))

        return recs

    def build_account_health_snapshot(self, days=7, platform=None, account_id=None):
        """
        Build account-level health assessment.

        Health score heuristic (0-100):
        - Conversion efficiency (30%): conversions > 0 and CPA reasonable
        - Trend direction (25%): improvements vs deterioration in spend/conv/ctr
        - Creative health (20%): ratio of healthy vs fatigued creatives
        - Waste ratio (15%): spend on zero-conversion campaigns
        - CTR quality (10%): average CTR vs threshold

        Labels:
        - strong: score >= 70
        - stable: score >= 45
        - at_risk: score >= 25
        - weak: score < 25
        """
        dashboard = self._get_dashboard_data(days, account_id=account_id)
        campaigns = self._get_all_campaigns(dashboard, platform)
        creatives = self._get_creatives(days, account_id=account_id)
        comparison = dashboard.get("comparison", {})
        changes = comparison.get("changes", {})
        summary = dashboard.get("summary", {}).get("total", {})

        spend = summary.get("spend", 0)
        conversions = summary.get("conversions", 0)
        cpa = summary.get("cpa", 0)
        ctr = summary.get("ctr", 0)

        # ── Component 1: Conversion Efficiency (0-100, weight 30%) ──
        if spend == 0:
            conv_score = 50  # no data, neutral
        elif conversions == 0:
            conv_score = 0
        elif cpa <= self.CPA_GOOD_THRESHOLD:
            conv_score = 100
        elif cpa <= self.CPA_HIGH_THRESHOLD:
            conv_score = max(20, 100 - (cpa / self.CPA_HIGH_THRESHOLD) * 80)
        else:
            conv_score = max(0, 20 - (cpa - self.CPA_HIGH_THRESHOLD))

        # ── Component 2: Trend Direction (0-100, weight 25%) ──
        trend_score = 50  # neutral baseline
        spend_change = changes.get("spend", 0)
        conv_change = changes.get("conversions", 0)
        click_change = changes.get("clicks", 0)
        if conv_change > 10:
            trend_score += 20
        elif conv_change < -10:
            trend_score -= 20
        if spend_change > 20 and conv_change <= 0:
            trend_score -= 15  # spending more without results
        if click_change > 10:
            trend_score += 10
        trend_score = max(0, min(100, trend_score))

        # ── Component 3: Creative Health (0-100, weight 20%) ──
        if creatives:
            healthy = sum(1 for c in creatives if c.get("fatigue_status") == "healthy")
            creative_score = round((healthy / len(creatives)) * 100)
        else:
            creative_score = 50  # no data, neutral

        # ── Component 4: Waste Ratio (0-100, weight 15%) ──
        active_campaigns = [c for c in campaigns if (c.get("status", "") or "").upper() in ("ACTIVE", "ENABLED")]
        if active_campaigns:
            wasting = sum(1 for c in active_campaigns
                         if c.get("spend", 0) > self.SPEND_WASTE_THRESHOLD and c.get("conversions", 0) == 0)
            waste_score = max(0, 100 - (wasting / len(active_campaigns)) * 100)
        else:
            waste_score = 50

        # ── Component 5: CTR Quality (0-100, weight 10%) ──
        if ctr >= self.CTR_GOOD_THRESHOLD:
            ctr_score = 100
        elif ctr >= self.CTR_LOW_THRESHOLD:
            ctr_score = 50 + (ctr - self.CTR_LOW_THRESHOLD) / (self.CTR_GOOD_THRESHOLD - self.CTR_LOW_THRESHOLD) * 50
        elif ctr > 0:
            ctr_score = (ctr / self.CTR_LOW_THRESHOLD) * 50
        else:
            ctr_score = 0 if spend > 0 else 50

        # ── Weighted Score ──
        health_score = round(
            conv_score * 0.30 +
            trend_score * 0.25 +
            creative_score * 0.20 +
            waste_score * 0.15 +
            ctr_score * 0.10
        )
        health_score = max(0, min(100, health_score))

        # ── Label ──
        if health_score >= 70:
            label = "strong"
        elif health_score >= 45:
            label = "stable"
        elif health_score >= 25:
            label = "at_risk"
        else:
            label = "weak"

        return {
            "label": label,
            "score": health_score,
            "components": {
                "conversion_efficiency": round(conv_score),
                "trend_direction": round(trend_score),
                "creative_health": round(creative_score),
                "waste_ratio": round(waste_score),
                "ctr_quality": round(ctr_score),
            },
            "metrics": {
                "spend": spend,
                "conversions": conversions,
                "cpa": cpa,
                "ctr": ctr,
                "active_campaigns": len(active_campaigns) if campaigns else 0,
                "total_creatives": len(creatives),
            },
            "changes": changes,
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ══════════════════════════════════════════════════════════
    # PERSISTENCE (optional, lightweight)
    # ══════════════════════════════════════════════════════════

    def save_insight(self, insight, account_id=None):
        """Persist an insight to the database for history/alerting."""
        import json
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO ai_coach_insights
                   (insight_type, severity, entity_type, entity_name, title, message,
                    recommendation, payload_json, period_days, platform)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (insight.get("type", ""), insight.get("severity", "info"),
                 insight.get("entity_type", ""), insight.get("entity_name", ""),
                 insight.get("title", ""), insight.get("message", ""),
                 insight.get("recommendation", ""),
                 json.dumps(insight.get("supporting_metrics", {})),
                 insight.get("period_days", 7), insight.get("platform")),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_insights(self, limit=20):
        """Get recently persisted insights."""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM ai_coach_insights ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ══════════════════════════════════════════════════════════

    def _get_dashboard_data(self, days, account_id=None):
        """Get dashboard data for the given period."""
        if not self.dashboard_service:
            return {"summary": {"total": {}, "meta": {}, "google": {}},
                    "campaigns": {"meta": [], "google": []}, "comparison": {}}
        range_key = "today" if days <= 1 else ("7d" if days <= 7 else "30d")
        try:
            return self.dashboard_service.get_dashboard_data(range_key, account_id=account_id)
        except Exception:
            return {"summary": {"total": {}, "meta": {}, "google": {}},
                    "campaigns": {"meta": [], "google": []}, "comparison": {}}

    def _get_all_campaigns(self, dashboard, platform=None):
        """Extract all campaigns from dashboard data."""
        campaigns = dashboard.get("campaigns", {})
        result = []
        if platform != "google":
            result.extend(campaigns.get("meta", []))
        if platform != "meta":
            result.extend(campaigns.get("google", []))
        return result

    def _get_creatives(self, days, account_id=None):
        """Get creative data from creative service."""
        if not self.creative_service:
            return []
        try:
            return self.creative_service.get_creatives(days=days, account_id=account_id)
        except Exception:
            return []

    def _build_headline(self, spend, conversions, cpa, changes, days):
        """Build a natural language headline summarizing account state."""
        period = f"last {days} days" if days > 1 else "today"

        if spend == 0:
            return f"No spend data available for the {period}."

        if conversions == 0:
            return f"${spend:.2f} spent over the {period} with no conversions yet. Action needed."

        conv_change = changes.get("conversions", 0)
        spend_change = changes.get("spend", 0)

        if conv_change > 20:
            trend = "Conversions are trending up significantly"
        elif conv_change > 0:
            trend = "Conversions are improving"
        elif conv_change < -20:
            trend = "Conversions have dropped significantly"
        elif conv_change < 0:
            trend = "Conversions have slightly declined"
        else:
            trend = "Performance is stable"

        return f"{trend} over the {period}. {conversions} conversions at ${cpa:.2f} CPA from ${spend:.2f} total spend."

    def _build_summary_bullets(self, summary, changes, campaigns, creatives, days):
        """Build concise summary bullet points."""
        bullets = []
        spend = summary.get("spend", 0)
        conversions = summary.get("conversions", 0)
        cpa = summary.get("cpa", 0)

        # Spend summary
        spend_change = changes.get("spend", 0)
        direction = "up" if spend_change > 0 else ("down" if spend_change < 0 else "flat")
        bullets.append(f"Total spend: ${spend:.2f} ({direction} {abs(spend_change):.0f}% vs prior period)")

        # Conversions
        conv_change = changes.get("conversions", 0)
        bullets.append(f"Conversions: {conversions} ({'+' if conv_change > 0 else ''}{conv_change:.0f}% vs prior)")

        # Active campaigns
        active = [c for c in campaigns if (c.get("status", "") or "").upper() in ("ACTIVE", "ENABLED")]
        bullets.append(f"Active campaigns: {len(active)} of {len(campaigns)} total")

        # Creative health
        if creatives:
            fatigued = sum(1 for c in creatives if c.get("fatigue_status") in ("fatigued", "critical"))
            if fatigued > 0:
                bullets.append(f"Creative health: {fatigued} creative(s) showing fatigue signals")
            else:
                bullets.append(f"Creative health: All {len(creatives)} creatives healthy")

        # Waste alert
        wasting = [c for c in active if c.get("spend", 0) > self.SPEND_WASTE_THRESHOLD and c.get("conversions", 0) == 0]
        if wasting:
            waste_total = sum(c.get("spend", 0) for c in wasting)
            bullets.append(f"Waste alert: ${waste_total:.2f} spent across {len(wasting)} campaign(s) with no conversions")

        return bullets

    def _find_top_campaign(self, campaigns):
        """Find best performing campaign."""
        converting = [c for c in campaigns if c.get("conversions", 0) > 0]
        if not converting:
            return None
        best = min(converting, key=lambda c: c.get("cpa", float("inf")))
        return {
            "name": best.get("name", ""),
            "spend": best.get("spend", 0),
            "conversions": best.get("conversions", 0),
            "cpa": best.get("cpa", 0),
            "ctr": best.get("ctr", 0),
        }

    def _find_top_creative(self, creatives):
        """Find best performing creative."""
        if not creatives:
            return None
        best = max(creatives, key=lambda c: c.get("score", 0))
        if best.get("score", 0) == 0:
            return None
        return {
            "name": best.get("name", ""),
            "score": best.get("score", 0),
            "conversions": best.get("conversions", 0),
            "ctr": best.get("ctr", 0),
            "spend": best.get("spend", 0),
        }

    def _analyze_account_level(self, days):
        """Generate account-level recommendations."""
        dashboard = self._get_dashboard_data(days)
        comparison = dashboard.get("comparison", {})
        changes = comparison.get("changes", {})
        summary = dashboard.get("summary", {}).get("total", {})
        recs = []
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        spend_change = changes.get("spend", 0)
        conv_change = changes.get("conversions", 0)

        # ── Trend Improvement ──
        if conv_change > 20 and spend_change <= conv_change:
            recs.append(self._make_rec(
                rec_type="trend_improvement",
                severity="success",
                title="Account performance is improving",
                message=f"Conversions up {conv_change:.0f}% vs prior period while spend is {'stable' if abs(spend_change) < 5 else 'controlled'}.",
                recommendation="Current strategy is working. Consider maintaining allocation and monitoring.",
                entity_type="account",
                entity_name="Account",
                metrics={"spend_change": spend_change, "conv_change": conv_change},
                impact=conv_change,
                created_at=now,
            ))

        # ── Trend Deterioration ──
        if conv_change < -20:
            recs.append(self._make_rec(
                rec_type="trend_deterioration",
                severity="warning",
                title="Account performance is declining",
                message=f"Conversions dropped {abs(conv_change):.0f}% vs prior period{' while spend increased' if spend_change > 5 else ''}.",
                recommendation="Review campaign targeting, creative freshness, and budget allocation.",
                entity_type="account",
                entity_name="Account",
                metrics={"spend_change": spend_change, "conv_change": conv_change},
                impact=abs(conv_change),
                created_at=now,
            ))

        # ── Efficiency deterioration (spending more, not converting more) ──
        if spend_change > 15 and conv_change < 5 and summary.get("spend", 0) > 50:
            recs.append(self._make_rec(
                rec_type="efficiency_decline",
                severity="warning",
                title="Spending more without proportional results",
                message=f"Spend increased {spend_change:.0f}% but conversions only changed {conv_change:+.0f}%.",
                recommendation="Audit budget allocation. Shift spend from underperformers to efficient campaigns.",
                entity_type="account",
                entity_name="Account",
                metrics={"spend_change": spend_change, "conv_change": conv_change,
                         "spend": summary.get("spend", 0)},
                impact=spend_change,
                created_at=now,
            ))

        return recs

    def _analyze_cross_platform(self, days):
        """Generate cross-platform channel comparison recommendations."""
        recs = []
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            from app.services.cross_platform_service import CrossPlatformService
            cp = CrossPlatformService()
            opps = cp.detect_channel_opportunities(days)
            for opp in opps.get("opportunities", []):
                opp_type = opp.get("type", "")
                if opp_type == "channel_efficiency":
                    recs.append(self._make_rec(
                        rec_type="channel_efficiency",
                        severity="success",
                        title=opp["title"],
                        message=opp["message"],
                        recommendation=f"Consider reallocating experimental budget from {opp.get('from_platform', '')} to {opp.get('to_platform', '')}.",
                        entity_type="cross_platform",
                        entity_name=f"{opp.get('from_platform', '')} vs {opp.get('to_platform', '')}",
                        metrics={"confidence": opp.get("confidence", "medium")},
                        impact=30,
                        created_at=now,
                    ))
                elif opp_type == "concentration_risk":
                    recs.append(self._make_rec(
                        rec_type="channel_risk",
                        severity="warning",
                        title=opp["title"],
                        message=opp["message"],
                        recommendation="Diversify spend across channels to reduce platform dependency.",
                        entity_type="cross_platform",
                        entity_name="Channel Balance",
                        metrics={"confidence": opp.get("confidence", "medium")},
                        impact=20,
                        created_at=now,
                    ))
                elif opp_type == "engagement_gap":
                    recs.append(self._make_rec(
                        rec_type="channel_shift_opportunity",
                        severity="info",
                        title=opp["title"],
                        message=opp["message"],
                        recommendation=f"Review creative strategy on the lower-performing platform.",
                        entity_type="cross_platform",
                        entity_name=opp.get("to_platform", ""),
                        metrics={"confidence": opp.get("confidence", "medium")},
                        impact=15,
                        created_at=now,
                    ))
        except Exception:
            pass
        return recs

    @staticmethod
    def _make_rec(rec_type, severity, title, message, recommendation,
                  entity_type, entity_name, metrics, impact, created_at):
        """Build a standardized recommendation dict."""
        return {
            "type": rec_type,
            "severity": severity,
            "title": title,
            "message": message,
            "recommendation": recommendation,
            "entity_type": entity_type,
            "entity_name": entity_name,
            "supporting_metrics": metrics,
            "_impact": impact,  # internal sort key, removed before output
            "created_at": created_at,
        }
