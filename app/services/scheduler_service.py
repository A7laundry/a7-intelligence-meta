"""Scheduler Service — Structured job execution for cron/CLI operations.

Each job is independently callable from Python, CLI, or cron.
All executions are logged to operations_log for observability.

Usage from CLI:
  python run.py --snapshot
  python run.py --ai-refresh
  python run.py --alerts-refresh
  python run.py --daily-briefing
  python run.py --end-of-day

Usage from cron:
  0 */4 * * * cd /path/to/project && .venv/bin/python run.py --snapshot
  0 8 * * *   cd /path/to/project && .venv/bin/python run.py --daily-briefing
  0 22 * * *  cd /path/to/project && .venv/bin/python run.py --end-of-day
"""

import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import init_db, get_connection


class SchedulerService:
    """Manages scheduled job execution with logging and observability."""

    def run_snapshot_job(self):
        """Collect metrics snapshot from live APIs and store in database."""
        started = datetime.utcnow()
        try:
            init_db()
            from app.services.dashboard_service import DashboardService
            svc = DashboardService()
            data = svc.fetch_and_store("today")
            spend = data.get("summary", {}).get("total", {}).get("spend", 0)
            conv = data.get("summary", {}).get("total", {}).get("conversions", 0)
            msg = f"Snapshot stored. Spend: ${spend:.2f}, Conversions: {conv}"
            self._log_operation("snapshot", "success", msg, {"spend": spend, "conversions": conv}, started)
            return {"status": "success", "message": msg, "spend": spend, "conversions": conv}
        except Exception as e:
            msg = f"Snapshot failed: {str(e)}"
            self._log_operation("snapshot", "failed", msg, {"error": str(e)}, started)
            # Create alert for snapshot failure
            self._create_failure_alert("snapshot_failure", msg)
            return {"status": "failed", "message": msg}

    def run_ai_refresh_job(self):
        """Refresh AI Coach, creative intelligence, and budget intelligence."""
        started = datetime.utcnow()
        results = {}
        try:
            init_db()

            # AI Coach
            try:
                from app.services.ai_coach_service import AICoachService
                coach = AICoachService()
                briefing = coach.generate_daily_briefing(days=7)
                recs = coach.generate_recommendations(days=7)
                results["ai_coach"] = {"headline": briefing.get("headline", ""), "recommendations": len(recs)}
            except Exception as e:
                results["ai_coach"] = {"error": str(e)}

            # Creative Intelligence
            try:
                from app.services.creative_service import CreativeService
                cs = CreativeService()
                if cs.meta_available:
                    collect = cs.collect_creatives()
                    results["creatives"] = collect
                else:
                    results["creatives"] = {"skipped": "Meta not available"}
            except Exception as e:
                results["creatives"] = {"error": str(e)}

            # Budget Intelligence
            try:
                from app.services.budget_intelligence_service import BudgetIntelligenceService
                bi = BudgetIntelligenceService()
                eff = bi.compute_efficiency_score(days=7)
                results["budget"] = {"efficiency_score": eff.get("score", 0)}
            except Exception as e:
                results["budget"] = {"error": str(e)}

            msg = f"AI refresh complete. Coach: {results.get('ai_coach', {}).get('recommendations', 0)} recs"
            self._log_operation("ai_refresh", "success", msg, results, started)
            return {"status": "success", "message": msg, "results": results}
        except Exception as e:
            msg = f"AI refresh failed: {str(e)}"
            self._log_operation("ai_refresh", "failed", msg, {"error": str(e)}, started)
            return {"status": "failed", "message": msg}

    def run_alert_refresh_job(self):
        """Recompute alerts and persist/deliver new ones."""
        started = datetime.utcnow()
        try:
            init_db()
            from app.services.alerts_service import AlertsService
            svc = AlertsService()
            new_alerts = svc.generate_all_alerts(days=7)
            msg = f"Alert refresh complete. {len(new_alerts)} new alert(s)"
            self._log_operation("alert_refresh", "success", msg,
                                {"new_alerts": len(new_alerts)}, started)
            return {"status": "success", "message": msg, "new_alerts": len(new_alerts)}
        except Exception as e:
            msg = f"Alert refresh failed: {str(e)}"
            self._log_operation("alert_refresh", "failed", msg, {"error": str(e)}, started)
            return {"status": "failed", "message": msg}

    def run_daily_briefing_job(self):
        """Generate and store daily executive briefing."""
        started = datetime.utcnow()
        try:
            init_db()
            from app.services.ai_coach_service import AICoachService
            from app.services.growth_score_service import GrowthScoreService

            coach = AICoachService()
            growth = GrowthScoreService()

            briefing = coach.generate_daily_briefing(days=7)
            score = growth.build_growth_score(days=7)

            payload = {
                "briefing": briefing,
                "growth_score": score["score"],
                "growth_label": score["label"],
                "summary": score["summary"],
            }
            msg = f"Daily briefing: Growth Score {score['score']}/100 ({score['label']}). {briefing.get('headline', '')}"
            self._log_operation("daily_briefing", "success", msg, payload, started)
            return {"status": "success", "message": msg, "payload": payload}
        except Exception as e:
            msg = f"Daily briefing failed: {str(e)}"
            self._log_operation("daily_briefing", "failed", msg, {"error": str(e)}, started)
            return {"status": "failed", "message": msg}

    def run_end_of_day_summary_job(self):
        """Generate end-of-day summary with key metrics."""
        started = datetime.utcnow()
        try:
            init_db()
            from app.services.dashboard_service import DashboardService
            from app.services.growth_score_service import GrowthScoreService
            from app.services.ai_coach_service import AICoachService

            ds = DashboardService()
            data = ds.get_dashboard_data("today")
            summary = data.get("summary", {}).get("total", {})

            growth = GrowthScoreService()
            score = growth.build_growth_score(days=1)

            coach = AICoachService()
            briefing = coach.generate_daily_briefing(days=1)

            payload = {
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
                "spend": summary.get("spend", 0),
                "conversions": summary.get("conversions", 0),
                "cpa": summary.get("cpa", 0),
                "growth_score": score["score"],
                "growth_label": score["label"],
                "top_campaign": briefing.get("top_campaign"),
                "top_creative": briefing.get("top_creative"),
                "top_risk": briefing.get("top_risk", {}).get("title") if briefing.get("top_risk") else None,
                "top_opportunity": briefing.get("top_opportunity", {}).get("title") if briefing.get("top_opportunity") else None,
            }
            spend = summary.get("spend", 0)
            conv = summary.get("conversions", 0)
            msg = f"EOD: ${spend:.2f} spend, {conv} conversions, Growth Score {score['score']}/100"
            self._log_operation("end_of_day", "success", msg, payload, started)
            return {"status": "success", "message": msg, "payload": payload}
        except Exception as e:
            msg = f"EOD summary failed: {str(e)}"
            self._log_operation("end_of_day", "failed", msg, {"error": str(e)}, started)
            return {"status": "failed", "message": msg}

    def run_account_automation(self, account_id):
        """Generate automation proposals and execute approved actions for one account.

        Proposals are tagged with account_id at generation time.
        Execution is scoped strictly to that account — no cross-account leakage.
        Creates an automation_runs record before execution and finalizes it on completion.
        """
        started = datetime.utcnow()
        results = {}
        run_id = self._create_run(account_id, started)
        try:
            init_db()
            from app.services.automation_engine import AutomationEngine
            engine = AutomationEngine()

            # Generate & queue proposals for this account
            queued = engine.generate_and_queue(days=7, account_id=account_id)
            results["queued"] = queued.get("queued_count", 0)
            results["blocked"] = queued.get("blocked_count", 0)
            proposals_generated = queued.get("total_proposals", 0)

            # Execute only approved actions belonging to this account
            executed = engine.execute_approved_actions_for_account(account_id)
            actions_executed = executed.get("executed_count", 0)
            actions_failed = sum(
                1 for r in executed.get("results", []) if not r.get("success")
            )
            results["executed"] = actions_executed
            results["failed"] = actions_failed

            self._finalize_run(run_id, proposals_generated, actions_executed, actions_failed, "success")

            msg = (
                f"Account {account_id} automation: "
                f"{results['queued']} queued, {actions_executed} executed"
            )
            self._log_operation("automation", "success", msg,
                                {"account_id": account_id, **results}, started)
            return {"status": "success", "message": msg, "account_id": account_id,
                    "run_id": run_id, **results}
        except Exception as e:
            self._finalize_run(run_id, 0, 0, 0, "failed")
            msg = f"Account {account_id} automation failed: {str(e)}"
            self._log_operation("automation", "failed", msg,
                                {"account_id": account_id, "error": str(e)}, started)
            return {"status": "failed", "message": msg, "account_id": account_id, "run_id": run_id}

    def _create_run(self, account_id, started_at):
        """Insert a new automation run record with status='running'. Returns run id."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO automation_runs (account_id, started_at, status) VALUES (?, ?, 'running')",
                (account_id, started_at.strftime("%Y-%m-%dT%H:%M:%SZ"))
            )
            conn.commit()
            return cursor.lastrowid
        except Exception:
            return None
        finally:
            conn.close()

    def _finalize_run(self, run_id, proposals_generated, actions_executed, actions_failed, status):
        """Update automation run record on completion."""
        if run_id is None:
            return
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE automation_runs
                   SET finished_at = ?, proposals_generated = ?, actions_executed = ?,
                       actions_failed = ?, status = ?
                   WHERE id = ?""",
                (datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                 proposals_generated, actions_executed, actions_failed, status, run_id)
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def run_all_accounts_automation(self):
        """Run automation for every active ad account sequentially.

        Each account is processed in isolation — no cross-account action execution.
        """
        started = datetime.utcnow()
        try:
            init_db()
            from app.services.account_service import AccountService
            accounts = AccountService.get_all()
            if not accounts:
                msg = "No ad accounts found — automation skipped"
                self._log_operation("automation_all", "success", msg, {}, started)
                return {"status": "success", "message": msg, "accounts_processed": 0}

            account_results = []
            for acc in accounts:
                result = self.run_account_automation(acc["id"])
                account_results.append(result)

            total_queued = sum(r.get("queued", 0) for r in account_results)
            total_executed = sum(r.get("executed", 0) for r in account_results)
            msg = (
                f"All-accounts automation: {len(accounts)} accounts, "
                f"{total_queued} queued, {total_executed} executed"
            )
            payload = {
                "accounts_processed": len(accounts),
                "total_queued": total_queued,
                "total_executed": total_executed,
                "per_account": account_results,
            }
            self._log_operation("automation_all", "success", msg, payload, started)
            return {"status": "success", "message": msg, **payload}
        except Exception as e:
            msg = f"All-accounts automation failed: {str(e)}"
            self._log_operation("automation_all", "failed", msg, {"error": str(e)}, started)
            return {"status": "failed", "message": msg}

    def get_operations_status(self):
        """Get latest status for each operation type."""
        conn = get_connection()
        try:
            types = ["snapshot", "ai_refresh", "alert_refresh", "daily_briefing", "end_of_day",
                     "automation", "automation_all"]
            status = {}
            for op_type in types:
                row = conn.execute(
                    """SELECT status, message, started_at, finished_at
                       FROM operations_log WHERE operation_type = ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (op_type,)
                ).fetchone()
                if row:
                    status[op_type] = dict(row)
                else:
                    status[op_type] = {"status": "never_run", "message": "Not yet executed"}
            return status
        except Exception:
            return {}
        finally:
            conn.close()

    def get_operations_history(self, limit=50):
        """Get recent operations log entries."""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM operations_log ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if "payload_json" in d:
                    try:
                        d["payload"] = json.loads(d["payload_json"])
                    except Exception:
                        d["payload"] = {}
                    del d["payload_json"]
                result.append(d)
            return result
        except Exception:
            return []
        finally:
            conn.close()

    def _log_operation(self, op_type, status, message, payload, started_at):
        """Persist operation execution to log."""
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO operations_log
                   (operation_type, status, message, payload_json, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (op_type, status, message, json.dumps(payload, default=str),
                 started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _create_failure_alert(self, alert_type, message):
        """Create a critical alert for job failures."""
        try:
            from app.services.alerts_service import AlertsService
            svc = AlertsService()
            alert = svc._make_alert(
                alert_type=alert_type,
                severity="critical",
                entity_type="system",
                entity_name="Scheduler",
                title=f"Job failed: {alert_type}",
                message=message,
            )
            if not svc._is_duplicate(alert):
                svc._persist(alert)
                svc._deliver(alert)
        except Exception:
            pass
