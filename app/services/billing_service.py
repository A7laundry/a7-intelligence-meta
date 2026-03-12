"""Billing Service — plan lookup, usage tracking, and limit enforcement."""

from datetime import datetime

from app.db.init_db import get_connection


class BillingService:
    DEFAULT_ORG_ID = 1

    # ── Plan & Subscription ───────────────────────────────────────

    def get_plan(self, org_id: int = DEFAULT_ORG_ID) -> dict:
        """Return current plan + subscription for the organization."""
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT p.id, p.name, p.price,
                          p.accounts_limit, p.automation_runs_limit, p.copilot_queries_limit,
                          s.status, s.created_at AS subscribed_at
                   FROM subscriptions s
                   JOIN plans p ON p.id = s.plan_id
                   WHERE s.organization_id = ?""",
                (org_id,),
            ).fetchone()
            if not row:
                return self._starter_fallback()
            return {
                "plan_id":                 row["id"],
                "plan_name":               row["name"],
                "price":                   row["price"],
                "accounts_limit":          row["accounts_limit"],
                "automation_runs_limit":   row["automation_runs_limit"],
                "copilot_queries_limit":   row["copilot_queries_limit"],
                "status":                  row["status"],
                "subscribed_at":           row["subscribed_at"],
            }
        except Exception:
            return self._starter_fallback()
        finally:
            conn.close()

    def _starter_fallback(self) -> dict:
        return {
            "plan_id": None, "plan_name": "Starter", "price": 0.0,
            "accounts_limit": 2, "automation_runs_limit": 100,
            "copilot_queries_limit": 200, "status": "active",
        }

    # ── Usage Tracking ────────────────────────────────────────────

    def track_usage(self, metric: str, value: int = 1, org_id: int = DEFAULT_ORG_ID) -> None:
        """Increment usage counter for metric in the current month period."""
        period = datetime.utcnow().strftime("%Y-%m")
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO usage_metrics (organization_id, metric, value, period) VALUES (?,?,?,?)",
                (org_id, metric, value, period),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def get_usage(self, org_id: int = DEFAULT_ORG_ID, period: str = None) -> dict:
        """Return aggregated usage for the given period (defaults to current month)."""
        if period is None:
            period = datetime.utcnow().strftime("%Y-%m")
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT metric, COALESCE(SUM(value), 0) AS total
                   FROM usage_metrics
                   WHERE organization_id = ? AND period = ?
                   GROUP BY metric""",
                (org_id, period),
            ).fetchall()
            usage = {r["metric"]: r["total"] for r in rows}
            # Count connected accounts directly
            acc_count = conn.execute(
                "SELECT COUNT(*) FROM ad_accounts WHERE status='active'"
            ).fetchone()[0]
            return {
                "period":             period,
                "copilot_queries":    usage.get("copilot_query", 0),
                "automation_runs":    usage.get("automation_run", 0),
                "accounts_connected": acc_count,
            }
        except Exception:
            return {"period": period, "copilot_queries": 0, "automation_runs": 0, "accounts_connected": 0}
        finally:
            conn.close()

    # ── Limit Checks ──────────────────────────────────────────────

    def check_account_limit(self, org_id: int = DEFAULT_ORG_ID) -> dict:
        """Check whether a new account can be connected."""
        plan = self.get_plan(org_id)
        limit = plan["accounts_limit"]
        conn = get_connection()
        try:
            current = conn.execute(
                "SELECT COUNT(*) FROM ad_accounts WHERE status='active'"
            ).fetchone()[0]
        except Exception:
            current = 0
        finally:
            conn.close()
        allowed = (limit is None) or (current < limit)
        return {"allowed": allowed, "current": current, "limit": limit}

    def check_copilot_usage(self, org_id: int = DEFAULT_ORG_ID) -> dict:
        """Check whether a Copilot query is within plan limit for current month."""
        plan = self.get_plan(org_id)
        limit = plan["copilot_queries_limit"]
        usage = self.get_usage(org_id)
        used = usage["copilot_queries"]
        allowed = (limit is None) or (used < limit)
        return {"allowed": allowed, "used": used, "limit": limit}

    def check_automation_usage(self, org_id: int = DEFAULT_ORG_ID) -> dict:
        """Check whether an automation run is within plan limit for current month."""
        plan = self.get_plan(org_id)
        limit = plan["automation_runs_limit"]
        usage = self.get_usage(org_id)
        used = usage["automation_runs"]
        allowed = (limit is None) or (used < limit)
        return {"allowed": allowed, "used": used, "limit": limit}

    # ── Dashboard Summary ─────────────────────────────────────────

    def get_plan_usage_summary(self, org_id: int = DEFAULT_ORG_ID) -> dict:
        """Return full usage + limits summary suitable for the dashboard panel."""
        plan = self.get_plan(org_id)
        usage = self.get_usage(org_id)

        def _meter(used, limit):
            if limit is None:
                return {"used": used, "limit": None, "pct": 0, "unlimited": True}
            pct = round(min(used / limit * 100, 100), 1) if limit > 0 else 0
            return {"used": used, "limit": limit, "pct": pct, "unlimited": False}

        return {
            "plan_name":      plan["plan_name"],
            "price":          plan["price"],
            "status":         plan["status"],
            "period":         usage["period"],
            "accounts":       _meter(usage["accounts_connected"], plan["accounts_limit"]),
            "automation":     _meter(usage["automation_runs"],    plan["automation_runs_limit"]),
            "copilot":        _meter(usage["copilot_queries"],    plan["copilot_queries_limit"]),
        }
