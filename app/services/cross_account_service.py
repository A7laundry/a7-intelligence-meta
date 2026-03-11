"""Cross-Account Service — Aggregates metrics across all ad accounts for global overview."""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import get_connection
from app.services.account_service import AccountService


class CrossAccountService:
    """Builds cross-account overview: aggregated metrics, insights, spend share."""

    def build_overview(self, days=7):
        """Return overview payload across all accounts."""
        accounts = AccountService.get_all()
        if not accounts:
            return {"accounts": [], "insights": {}, "totals": {}, "spend_share": {}}

        rows = []
        for acc in accounts:
            metrics = self._get_account_metrics(acc["id"], days)
            alerts_count = self._get_alerts_count(acc["id"])
            efficiency = self._get_efficiency_score(acc["id"], days)
            growth = self._get_growth_score(acc["id"], days)
            rows.append({
                "id": acc["id"],
                "account_name": acc["account_name"],
                "platform": acc["platform"],
                "external_account_id": acc.get("external_account_id", ""),
                "is_default": acc.get("is_default", 0),
                "spend": metrics["spend"],
                "impressions": metrics["impressions"],
                "clicks": metrics["clicks"],
                "ctr": metrics["ctr"],
                "conversions": metrics["conversions"],
                "cpa": metrics["cpa"],
                "efficiency_score": efficiency,
                "alerts_count": alerts_count,
                "growth_score": growth["score"],
                "growth_label": growth["label"],
            })

        totals = self._compute_totals(rows)
        insights = self._compute_insights(rows)
        spend_share = self._compute_spend_share(rows)

        return {
            "accounts": rows,
            "insights": insights,
            "totals": totals,
            "spend_share": spend_share,
            "period_days": days,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ── Private helpers ──────────────────────────────────────────

    def _get_account_metrics(self, account_id, days):
        """Aggregate spend/impressions/clicks/conversions from snapshots."""
        conn = get_connection()
        try:
            since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            row = conn.execute(
                """SELECT
                       COALESCE(SUM(spend), 0)       AS spend,
                       COALESCE(SUM(impressions), 0) AS impressions,
                       COALESCE(SUM(clicks), 0)      AS clicks,
                       COALESCE(SUM(conversions), 0) AS conversions
                   FROM daily_snapshots
                   WHERE account_id = ? AND date >= ?""",
                (account_id, since),
            ).fetchone()
            if not row:
                return {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0}
            spend = row["spend"] or 0
            impressions = row["impressions"] or 0
            clicks = row["clicks"] or 0
            conversions = row["conversions"] or 0
            return {
                "spend": round(spend, 2),
                "impressions": impressions,
                "clicks": clicks,
                "ctr": round(clicks / impressions * 100, 2) if impressions > 0 else 0,
                "conversions": conversions,
                "cpa": round(spend / conversions, 2) if conversions > 0 else 0,
            }
        except Exception:
            return {"spend": 0, "impressions": 0, "clicks": 0, "ctr": 0, "conversions": 0, "cpa": 0}
        finally:
            conn.close()

    def _get_alerts_count(self, account_id):
        """Count unresolved alerts for account."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE account_id = ? AND resolved = 0",
                (account_id,),
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0
        finally:
            conn.close()

    def _get_efficiency_score(self, account_id, days):
        """Get budget efficiency score for account (returns 0-100)."""
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            result = bi.compute_efficiency_score(days=days, account_id=account_id)
            return result.get("score", 0)
        except Exception:
            return 0

    def _get_growth_score(self, account_id, days):
        """Get growth score for account."""
        try:
            from app.services.growth_score_service import GrowthScoreService
            gs = GrowthScoreService()
            result = gs.build_growth_score(days=days, account_id=account_id)
            return {"score": result.get("score", 0), "label": result.get("label", "unknown")}
        except Exception:
            return {"score": 0, "label": "unknown"}

    def _compute_totals(self, rows):
        """Sum key metrics across all accounts."""
        total_spend = sum(r["spend"] for r in rows)
        total_conversions = sum(r["conversions"] for r in rows)
        total_alerts = sum(r["alerts_count"] for r in rows)
        total_impressions = sum(r["impressions"] for r in rows)
        total_clicks = sum(r["clicks"] for r in rows)
        return {
            "spend": round(total_spend, 2),
            "impressions": total_impressions,
            "clicks": total_clicks,
            "ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0,
            "conversions": total_conversions,
            "cpa": round(total_spend / total_conversions, 2) if total_conversions > 0 else 0,
            "alerts": total_alerts,
            "accounts": len(rows),
        }

    def _compute_insights(self, rows):
        """Detect cross-account patterns."""
        if not rows:
            return {}

        insights = {}

        # Best performing: most conversions; if tied, lowest CPA
        with_conversions = [r for r in rows if r["conversions"] > 0]
        if with_conversions:
            best = max(with_conversions, key=lambda r: (r["conversions"], -r["cpa"] if r["cpa"] > 0 else 0))
            insights["best_performing"] = {
                "id": best["id"],
                "name": best["account_name"],
                "reason": f"{best['conversions']} conversions at ${best['cpa']:.2f} CPA",
            }

        # Worst CPA: highest CPA with spend > 0
        with_spend = [r for r in rows if r["spend"] > 0]
        if with_spend:
            worst = max(with_spend, key=lambda r: r["cpa"] if r["conversions"] > 0 else 999999)
            insights["worst_cpa"] = {
                "id": worst["id"],
                "name": worst["account_name"],
                "reason": f"CPA ${worst['cpa']:.2f}" if worst["conversions"] > 0 else f"${worst['spend']:.2f} spend, 0 conversions",
            }

        # Highest alert concentration
        if any(r["alerts_count"] > 0 for r in rows):
            most_alerts = max(rows, key=lambda r: r["alerts_count"])
            if most_alerts["alerts_count"] > 0:
                insights["highest_alerts"] = {
                    "id": most_alerts["id"],
                    "name": most_alerts["account_name"],
                    "count": most_alerts["alerts_count"],
                    "reason": f"{most_alerts['alerts_count']} unresolved alert{'s' if most_alerts['alerts_count'] != 1 else ''}",
                }

        # Opportunity: high efficiency score + conversions > 0
        candidates = [r for r in rows if r["efficiency_score"] >= 60 and r["conversions"] > 0]
        if candidates:
            opp = max(candidates, key=lambda r: r["efficiency_score"])
            insights["opportunity"] = {
                "id": opp["id"],
                "name": opp["account_name"],
                "reason": f"Efficiency {opp['efficiency_score']}/100 — consider scaling budget",
            }

        return insights

    def get_account_status(self, account_id):
        """Return sync status for a single account (for header status pill)."""
        conn = get_connection()
        try:
            # Last snapshot date
            last_snap = conn.execute(
                "SELECT MAX(date) as last_date FROM daily_snapshots WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            last_snapshot = last_snap["last_date"] if last_snap else None

            # Campaigns count (latest snapshot)
            campaigns_count = conn.execute(
                """SELECT COUNT(DISTINCT campaign_id) FROM campaign_snapshots
                   WHERE account_id = ? AND date = (
                     SELECT MAX(date) FROM campaign_snapshots WHERE account_id = ?
                   )""",
                (account_id, account_id),
            ).fetchone()[0] or 0

            # Creatives count
            creatives_count = conn.execute(
                "SELECT COUNT(*) FROM creatives WHERE account_id = ?",
                (account_id,),
            ).fetchone()[0] or 0

            # Today's spend + conversions
            today = datetime.utcnow().strftime("%Y-%m-%d")
            today_row = conn.execute(
                """SELECT COALESCE(SUM(spend), 0) as spend, COALESCE(SUM(conversions), 0) as conv
                   FROM daily_snapshots WHERE account_id = ? AND date = ?""",
                (account_id, today),
            ).fetchone()
            spend_today = round(today_row["spend"], 2) if today_row else 0
            conversions_today = today_row["conv"] if today_row else 0

            # Active alerts
            alerts_active = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE account_id = ? AND resolved = 0",
                (account_id,),
            ).fetchone()[0] or 0

            # Freshness: fresh if snapshot within 24h, stale if 1-3 days, empty if no data
            freshness = "empty"
            if last_snapshot:
                try:
                    snap_date = datetime.strptime(last_snapshot, "%Y-%m-%d")
                    delta = (datetime.utcnow() - snap_date).days
                    freshness = "fresh" if delta <= 1 else "stale"
                except Exception:
                    freshness = "stale"

            return {
                "account_id": account_id,
                "last_snapshot": last_snapshot,
                "freshness": freshness,
                "campaigns_count": campaigns_count,
                "creatives_count": creatives_count,
                "spend_today": spend_today,
                "conversions_today": conversions_today,
                "alerts_active": alerts_active,
            }
        except Exception:
            return {"account_id": account_id, "freshness": "empty"}
        finally:
            conn.close()

    def _compute_spend_share(self, rows):
        """Build spend share data for doughnut chart."""
        total_spend = sum(r["spend"] for r in rows)
        labels = [r["account_name"] for r in rows]
        values = [r["spend"] for r in rows]
        percentages = [
            round(r["spend"] / total_spend * 100, 1) if total_spend > 0 else 0
            for r in rows
        ]
        return {"labels": labels, "values": values, "percentages": percentages, "total": round(total_spend, 2)}
