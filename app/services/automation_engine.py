"""Automation Engine — Safe, traceable execution of optimization actions.

Generates proposals from intelligence services, queues them for approval,
validates through guardrails, and executes with full audit logging.

Default mode is dry_run. Actions are simulated unless AUTOMATION_MODE=live.

TODO: Add automatic budget reallocation across platforms
TODO: Add creative generation with AI
TODO: Add auto-scaling campaigns based on forecast
TODO: Add multi-account orchestration
"""

import os
import time
from datetime import datetime, timedelta

from app.db.init_db import get_connection

_LIVE_MODE = os.environ.get("A7_AUTOMATION_LIVE", "0") == "1"


class AutomationEngine:
    """Controlled automation engine with approval workflow and audit trail."""

    # ── Action types ──
    VALID_ACTION_TYPES = {
        "pause_campaign", "increase_budget", "decrease_budget",
        "refresh_creative", "rotate_creative",
    }

    VALID_STATUSES = {"proposed", "approved", "rejected", "executed", "failed"}

    # ── Default guardrail configuration ──
    DEFAULT_CONFIG = {
        "execution_mode": "dry_run",
        "max_actions_per_run": 5,
        "max_budget_change_pct": 30,
        "min_confidence": "medium",
        "cooldown_hours": 24,
        "platform_allowlist": [],
        "campaign_blacklist": [],
        "global_enabled": True,
    }

    CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

    def __init__(self):
        self.config = self._load_config()

    def _load_config(self):
        """Load configuration from environment or defaults."""
        config = dict(self.DEFAULT_CONFIG)
        if os.environ.get("AUTOMATION_MODE"):
            config["execution_mode"] = os.environ["AUTOMATION_MODE"]
        if os.environ.get("MAX_BUDGET_CHANGE_PCT"):
            config["max_budget_change_pct"] = int(os.environ["MAX_BUDGET_CHANGE_PCT"])
        if os.environ.get("MAX_ACTIONS_PER_RUN"):
            config["max_actions_per_run"] = int(os.environ["MAX_ACTIONS_PER_RUN"])
        if os.environ.get("AUTOMATION_COOLDOWN_HOURS"):
            config["cooldown_hours"] = int(os.environ["AUTOMATION_COOLDOWN_HOURS"])
        if os.environ.get("AUTOMATION_CONFIDENCE"):
            config["min_confidence"] = os.environ["AUTOMATION_CONFIDENCE"]
        if os.environ.get("AUTOMATION_ENABLED"):
            config["global_enabled"] = os.environ["AUTOMATION_ENABLED"].lower() in ("true", "1", "yes")
        return config

    # ══════════════════════════════════════════════════════════
    # PROPOSAL GENERATION
    # ══════════════════════════════════════════════════════════

    def generate_action_proposals(self, days=7, platform=None):
        """Generate automation proposals from all intelligence sources.

        Sources: AI Coach, Budget Intelligence, Advanced Analytics, Cross-Platform.
        Returns proposals ready for queue insertion.
        """
        proposals = []

        # Source 1: Budget scaling opportunities
        proposals.extend(self._proposals_from_budget(days, platform))

        # Source 2: Waste / pause proposals
        proposals.extend(self._proposals_from_waste(days, platform))

        # Source 3: Creative fatigue proposals
        proposals.extend(self._proposals_from_creatives(days))

        # Source 4: Anomaly-driven proposals
        proposals.extend(self._proposals_from_anomalies(days))

        # Source 5: Cross-platform rebalancing
        proposals.extend(self._proposals_from_cross_platform(days))

        return proposals

    def generate_and_queue(self, days=7, platform=None, account_id=1):
        """Generate proposals, validate through guardrails, and persist to queue."""
        proposals = self.generate_action_proposals(days, platform)

        queued = []
        blocked = []

        for p in proposals:
            p["account_id"] = account_id
            validation = self.validate_action(p)
            if validation["allowed"]:
                p["status"] = "proposed"
                p["execution_mode"] = self.config["execution_mode"]
                action_id = self._persist_action(p)
                p["id"] = action_id
                queued.append(p)
                self._log_action(action_id, p, "proposed",
                                 f"Action queued: {p['action_type']} on {p['entity_name']}")
                self._notify("action_proposed", p)
            else:
                p["status"] = "blocked"
                p["blocked_reason"] = validation["reason"]
                blocked.append(p)

        return {
            "queued": queued,
            "blocked": blocked,
            "queued_count": len(queued),
            "blocked_count": len(blocked),
            "total_proposals": len(proposals),
            "execution_mode": self.config["execution_mode"],
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ══════════════════════════════════════════════════════════
    # APPROVAL WORKFLOW
    # ══════════════════════════════════════════════════════════

    def approve_action(self, action_id, account_id=None):
        """Approve a proposed action for execution.

        If account_id is provided, the action must belong to that account
        (prevents cross-account approval).
        """
        action = self._get_action(action_id)
        if not action:
            return {"success": False, "error": "Action not found"}
        if account_id is not None and action.get("account_id") != account_id:
            return {"success": False, "error": "Action does not belong to the specified account"}
        if action["status"] != "proposed":
            return {"success": False, "error": f"Cannot approve action in '{action['status']}' status"}

        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE automation_actions SET status = 'approved', approved_at = ? WHERE id = ?",
                (now, action_id)
            )
            conn.commit()
        finally:
            conn.close()

        self._log_action(action_id, dict(action), "approved",
                         f"Action approved: {action['action_type']} on {action['entity_name']}")
        self._notify("action_approved", dict(action))

        return {"success": True, "action_id": action_id, "status": "approved"}

    def reject_action(self, action_id):
        """Reject a proposed action."""
        action = self._get_action(action_id)
        if not action:
            return {"success": False, "error": "Action not found"}
        if action["status"] not in ("proposed", "approved"):
            return {"success": False, "error": f"Cannot reject action in '{action['status']}' status"}

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE automation_actions SET status = 'rejected' WHERE id = ?",
                (action_id,)
            )
            conn.commit()
        finally:
            conn.close()

        self._log_action(action_id, dict(action), "blocked",
                         f"Action rejected: {action['action_type']} on {action['entity_name']}")

        return {"success": True, "action_id": action_id, "status": "rejected"}

    # ══════════════════════════════════════════════════════════
    # EXECUTION ENGINE
    # ══════════════════════════════════════════════════════════

    def execute_action(self, action_id, account_id=None):
        """Execute a single approved action.

        If account_id is provided, the action must belong to that account
        (prevents cross-account execution).
        """
        action = self._get_action(action_id)
        if not action:
            return {"success": False, "error": "Action not found"}
        if account_id is not None and action.get("account_id") != account_id:
            return {"success": False, "error": "Action does not belong to the specified account"}
        if action["status"] != "approved":
            return {"success": False, "error": f"Cannot execute action in '{action['status']}' status. Must be 'approved'."}

        action = dict(action)
        start = time.time()

        # Re-validate through guardrails before execution
        validation = self.validate_action(action)
        if not validation["allowed"]:
            self._update_action_status(action_id, "failed")
            self._log_action(action_id, action, "blocked",
                             f"Blocked by guardrail: {validation['reason']}")
            return {"success": False, "error": f"Blocked by guardrail: {validation['reason']}"}

        execution_mode = action.get("execution_mode", self.config["execution_mode"])

        if execution_mode == "dry_run":
            # Simulate execution
            elapsed = int((time.time() - start) * 1000)
            self._update_action_status(action_id, "executed",
                                       executed_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
            self._log_action(action_id, action, "simulated",
                             f"[DRY RUN] Simulated {action['action_type']} on {action['entity_name']}",
                             elapsed)
            self._notify("action_executed", action)
            return {
                "success": True, "action_id": action_id, "status": "executed",
                "mode": "dry_run", "message": f"Simulated {action['action_type']} on {action['entity_name']}"
            }

        # Live execution
        try:
            result = self._execute_live(action)
            elapsed = int((time.time() - start) * 1000)
            self._update_action_status(action_id, "executed",
                                       executed_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
            self._log_action(action_id, action, "executed",
                             f"Executed {action['action_type']} on {action['entity_name']}: {result.get('message', 'OK')}",
                             elapsed)
            self._notify("action_executed", action)
            return {
                "success": True, "action_id": action_id, "status": "executed",
                "mode": "live", "message": result.get("message", "Executed successfully")
            }
        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            self._update_action_status(action_id, "failed")
            self._log_action(action_id, action, "failed",
                             f"Execution failed: {str(e)}", elapsed)
            self._notify("action_failed", action)
            return {"success": False, "action_id": action_id, "status": "failed", "error": str(e)}

    def execute_approved_actions(self):
        """Execute all approved actions respecting max_actions_per_run."""
        approved = self.get_actions(status="approved")
        results = []
        executed_count = 0

        for action in approved:
            if executed_count >= self.config["max_actions_per_run"]:
                break
            result = self.execute_action(action["id"])
            results.append(result)
            if result.get("success"):
                executed_count += 1

        return {
            "results": results,
            "executed_count": executed_count,
            "total_approved": len(approved),
            "max_per_run": self.config["max_actions_per_run"],
            "execution_mode": self.config["execution_mode"],
        }

    def execute_approved_actions_for_account(self, account_id):
        """Execute all approved actions for a specific account only.

        Enforces account isolation: actions from other accounts are never touched.
        """
        approved = self.get_actions(status="approved", account_id=account_id)
        results = []
        executed_count = 0

        for action in approved:
            if executed_count >= self.config["max_actions_per_run"]:
                break
            result = self.execute_action(action["id"], account_id=account_id)
            results.append(result)
            if result.get("success"):
                executed_count += 1

        return {
            "account_id": account_id,
            "results": results,
            "executed_count": executed_count,
            "total_approved": len(approved),
            "max_per_run": self.config["max_actions_per_run"],
            "execution_mode": self.config["execution_mode"],
        }

    def _execute_live(self, action):
        """Execute a live action against the appropriate API."""
        action_type = action["action_type"]
        platform = action.get("platform", "meta")

        if action_type == "pause_campaign":
            return self._execute_pause(action, platform)
        elif action_type in ("increase_budget", "decrease_budget"):
            return self._execute_budget_change(action, platform)
        elif action_type in ("refresh_creative", "rotate_creative"):
            return {"message": f"Creative action '{action_type}' logged for manual review"}
        else:
            return {"message": f"Unknown action type '{action_type}' — logged only"}

    def _execute_pause(self, action, platform):
        """Execute campaign pause via API."""
        if platform == "meta":
            try:
                from app.services.metrics_service import MetricsService
                svc = MetricsService()
                svc.update_campaign_status(action.get("entity_id", ""), "PAUSED")
                return {"message": f"Paused Meta campaign {action['entity_name']}"}
            except Exception as e:
                raise RuntimeError(f"Meta API pause failed: {e}")
        return {"message": f"Pause logged for {platform} campaign {action['entity_name']} (manual action required)"}

    def _execute_increase_budget(self, action: dict, account_id: int) -> dict:
        """Execute budget increase via Meta API (live) or return dry_run result."""
        campaign_id = action.get("entity_id") or action.get("campaign_id")
        params = action.get("action_params", {})
        new_budget = params.get("new_budget") or params.get("suggested_budget")

        if not campaign_id or not new_budget:
            return {"status": "skipped", "reason": "missing campaign_id or new_budget"}

        if not _LIVE_MODE:
            return {"status": "dry_run", "campaign_id": campaign_id, "new_budget": new_budget}

        try:
            from meta_client import MetaAdsClient
            client = MetaAdsClient()
            budget_cents = int(float(new_budget) * 100)
            result = client.update_campaign_budget(campaign_id, budget_cents)
            return {
                "status": "executed",
                "campaign_id": campaign_id,
                "new_budget": new_budget,
                "api_result": result,
            }
        except Exception as e:
            return {"status": "failed", "error": str(e), "campaign_id": campaign_id}

    def _execute_decrease_budget(self, action: dict, account_id: int) -> dict:
        """Execute budget decrease via Meta API (live) or return dry_run result."""
        campaign_id = action.get("entity_id") or action.get("campaign_id")
        params = action.get("action_params", {})
        new_budget = params.get("new_budget") or params.get("suggested_budget")

        if not campaign_id or not new_budget:
            return {"status": "skipped", "reason": "missing campaign_id or new_budget"}

        if not _LIVE_MODE:
            return {"status": "dry_run", "campaign_id": campaign_id, "new_budget": new_budget}

        try:
            from meta_client import MetaAdsClient
            client = MetaAdsClient()
            budget_cents = int(float(new_budget) * 100)
            result = client.update_campaign_budget(campaign_id, budget_cents)
            return {
                "status": "executed",
                "campaign_id": campaign_id,
                "new_budget": new_budget,
                "api_result": result,
            }
        except Exception as e:
            return {"status": "failed", "error": str(e), "campaign_id": campaign_id}

    def _execute_budget_change(self, action, platform):
        """Dispatch to increase/decrease handler; falls back to log-only for unknown platforms."""
        action_type = action.get("action_type", "")
        account_id = action.get("account_id", 1)

        if action_type == "increase_budget":
            result = self._execute_increase_budget(action, account_id)
        elif action_type == "decrease_budget":
            result = self._execute_decrease_budget(action, account_id)
        else:
            change_pct = action.get("suggested_change_pct", 0)
            direction = "increase" if change_pct > 0 else "decrease"
            result = {
                "status": "skipped",
                "message": f"Budget {direction} {abs(change_pct)}% logged for {action['entity_name']} "
                           f"on {platform} (manual action required)",
            }

        status = result.get("status", "unknown")
        entity = action.get("entity_name", "")
        return {"message": f"Budget change [{status}] for {entity} on {platform}: {result}"}

    # ══════════════════════════════════════════════════════════
    # GUARDRAILS
    # ══════════════════════════════════════════════════════════

    def validate_action(self, action):
        """Validate a single action against all guardrail rules."""
        if not self.config["global_enabled"]:
            return {"allowed": False, "reason": "Automation is globally disabled"}

        entity_name = action.get("entity_name", "")
        platform = action.get("platform", "meta")

        # Rule 1: Campaign blacklist
        if entity_name in self.config["campaign_blacklist"]:
            return {"allowed": False, "reason": f"Campaign '{entity_name}' is blacklisted"}

        # Rule 2: Platform allowlist
        if self.config["platform_allowlist"] and platform not in self.config["platform_allowlist"]:
            return {"allowed": False, "reason": f"Platform '{platform}' not in allowlist"}

        # Rule 3: Budget change cap
        change_pct = abs(action.get("suggested_change_pct", 0))
        if action.get("action_type") in ("increase_budget", "decrease_budget"):
            if change_pct > self.config["max_budget_change_pct"]:
                return {"allowed": False,
                        "reason": f"Budget change {change_pct}% exceeds max {self.config['max_budget_change_pct']}%"}

        # Rule 4: Confidence threshold
        confidence = action.get("confidence", "low")
        min_conf = self.config["min_confidence"]
        if self.CONFIDENCE_ORDER.get(confidence, 0) < self.CONFIDENCE_ORDER.get(min_conf, 1):
            return {"allowed": False,
                    "reason": f"Confidence '{confidence}' below minimum '{min_conf}'"}

        # Rule 5: Cooldown check
        if self._is_in_cooldown(entity_name, action.get("action_type", "")):
            return {"allowed": False,
                    "reason": f"Campaign '{entity_name}' is in {self.config['cooldown_hours']}h cooldown"}

        return {"allowed": True, "reason": None}

    def get_guardrails_config(self):
        """Return current effective guardrails configuration."""
        return {
            **self.config,
            "guardrails_active": True,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ══════════════════════════════════════════════════════════
    # QUEUE & PERSISTENCE
    # ══════════════════════════════════════════════════════════

    def get_actions(self, status=None, platform=None, limit=50, account_id=None):
        """Get actions from the queue, optionally filtered."""
        conn = get_connection()
        try:
            query = "SELECT * FROM automation_actions"
            params = []
            conditions = []
            if status:
                conditions.append("status = ?")
                params.append(status)
            if platform:
                conditions.append("platform = ?")
                params.append(platform)
            if account_id is not None:
                conditions.append("account_id = ?")
                params.append(account_id)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def get_pending_actions(self, account_id=None):
        """Get actions pending approval (proposed status)."""
        return self.get_actions(status="proposed", account_id=account_id)

    def get_action_summary(self, account_id=None):
        """Get action counts by status."""
        conn = get_connection()
        try:
            if account_id is not None:
                rows = conn.execute(
                    "SELECT status, COUNT(*) as count FROM automation_actions WHERE account_id = ? GROUP BY status",
                    (account_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT status, COUNT(*) as count FROM automation_actions GROUP BY status"
                ).fetchall()
            summary = {r["status"]: r["count"] for r in rows}
            summary["total"] = sum(summary.values())
            return summary
        except Exception:
            return {"total": 0}
        finally:
            conn.close()

    def get_logs(self, action_id=None, limit=50, account_id=None):
        """Get automation execution logs."""
        conn = get_connection()
        try:
            if action_id:
                rows = conn.execute(
                    "SELECT * FROM automation_logs WHERE action_id = ? ORDER BY created_at DESC LIMIT ?",
                    (action_id, limit)
                ).fetchall()
            elif account_id is not None:
                rows = conn.execute(
                    "SELECT * FROM automation_logs WHERE account_id = ? ORDER BY created_at DESC LIMIT ?",
                    (account_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM automation_logs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    # Default budget change percentages per action type
    _CHANGE_PCT_DEFAULTS = {
        "increase_budget": 20,
        "decrease_budget": -20,
        "pause_campaign": -100,
        "refresh_creative": 0,
        "rotate_creative": 0,
    }

    def generate_action_proposal(self, action_type, entity_name, entity_type="campaign",
                                  account_id=1, reason="Copilot suggestion",
                                  confidence="medium", platform="meta"):
        """Generate and queue a single action proposal from the Copilot.

        Creates a proposal dict, runs full guardrail validation via queue_proposal(),
        and persists it with status='proposed' for human review.

        Copilot NEVER executes actions directly — all execution goes through the
        Automation Engine approval workflow.

        Args:
            action_type:  One of VALID_ACTION_TYPES.
            entity_name:  Campaign or creative name from context.
            entity_type:  'campaign' | 'creative'
            account_id:   Account to scope the proposal to.
            reason:       Rationale from the Copilot answer.
            confidence:   'high' | 'medium' | 'low'
            platform:     'meta' | 'google'

        Returns:
            {"success": True,  "action_id": int}
            {"success": False, "reason": str, "action_id": None}
        """
        if action_type not in self.VALID_ACTION_TYPES:
            return {
                "success": False,
                "reason": f"action_type '{action_type}' is not supported",
                "action_id": None,
            }
        proposal = {
            "action_type": action_type,
            "platform": platform or "meta",
            "entity_type": entity_type or "campaign",
            "entity_id": "",
            "entity_name": entity_name,
            "reason": f"[Copilot] {reason}",
            "confidence": confidence or "medium",
            "suggested_change_pct": self._CHANGE_PCT_DEFAULTS.get(action_type, 0),
            "account_id": account_id or 1,
        }
        return self.queue_proposal(proposal)

    def create_proposal_from_copilot(self, action_type, entity_name, entity_type="campaign",
                                      account_id=1, reason="Copilot suggestion",
                                      confidence="medium", platform="meta",
                                      campaign_id=None, suggested_change_pct=None):
        """Named Copilot entry-point for Phase 6B — accepts campaign_id and suggested_change_pct.

        Validates action_type, builds a proposal dict (entity_id=campaign_id when provided),
        then routes through queue_proposal() for full guardrail validation and persistence.
        Copilot NEVER executes directly — proposals are created with status='proposed'.

        Returns:
            {"success": True,  "action_id": int}
            {"success": False, "reason": str, "action_id": None}
        """
        if action_type not in self.VALID_ACTION_TYPES:
            return {
                "success": False,
                "reason": f"action_type '{action_type}' is not supported",
                "action_id": None,
            }
        change_pct = (suggested_change_pct
                      if suggested_change_pct is not None
                      else self._CHANGE_PCT_DEFAULTS.get(action_type, 0))
        proposal = {
            "action_type": action_type,
            "platform": platform or "meta",
            "entity_type": entity_type or "campaign",
            "entity_id": campaign_id or "",
            "entity_name": entity_name,
            "reason": f"[Copilot] {reason}",
            "confidence": confidence or "medium",
            "suggested_change_pct": change_pct,
            "account_id": account_id or 1,
        }
        return self.queue_proposal(proposal)

    def queue_proposal(self, proposal):
        """Validate and queue a single manually constructed proposal.

        Used by the Copilot to convert suggested actions into automation queue entries.
        Runs full guardrail validation — blocked proposals are never persisted.

        Returns:
            {"success": True,  "action_id": int}
            {"success": False, "reason": str, "action_id": None}
        """
        validation = self.validate_action(proposal)
        if not validation["allowed"]:
            return {"success": False, "reason": validation["reason"], "action_id": None}

        proposal = dict(proposal)
        proposal["status"] = "proposed"
        proposal["execution_mode"] = self.config["execution_mode"]
        action_id = self._persist_action(proposal)
        proposal["id"] = action_id
        self._log_action(
            action_id, proposal, "proposed",
            f"Copilot proposal: {proposal.get('action_type')} on {proposal.get('entity_name')}"
        )
        self._notify("action_proposed", proposal)
        return {"success": True, "action_id": action_id}

    def get_runs(self, account_id=None, limit=20):
        """Get automation run history records."""
        conn = get_connection()
        try:
            if account_id is not None:
                rows = conn.execute(
                    "SELECT * FROM automation_runs WHERE account_id = ? ORDER BY started_at DESC LIMIT ?",
                    (account_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM automation_runs ORDER BY started_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def _persist_action(self, action):
        """Insert action into the queue and return its ID."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO automation_actions
                   (account_id, action_type, platform, entity_type, entity_id, entity_name,
                    reason, confidence, suggested_change_pct, status, execution_mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (action.get("account_id", 1),
                 action.get("action_type", ""),
                 action.get("platform", "meta"),
                 action.get("entity_type", "campaign"),
                 action.get("entity_id", ""),
                 action.get("entity_name", ""),
                 action.get("reason", ""),
                 action.get("confidence", "medium"),
                 action.get("suggested_change_pct", 0),
                 action.get("status", "proposed"),
                 action.get("execution_mode", self.config["execution_mode"]))
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def _get_action(self, action_id):
        """Get a single action by ID."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM automation_actions WHERE id = ?", (action_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _update_action_status(self, action_id, status, executed_at=None):
        """Update action status."""
        conn = get_connection()
        try:
            if executed_at:
                conn.execute(
                    "UPDATE automation_actions SET status = ?, executed_at = ? WHERE id = ?",
                    (status, executed_at, action_id)
                )
            else:
                conn.execute(
                    "UPDATE automation_actions SET status = ? WHERE id = ?",
                    (status, action_id)
                )
            conn.commit()
        finally:
            conn.close()

    def _log_action(self, action_id, action, status, message, execution_time_ms=0):
        """Write an audit log entry."""
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO automation_logs
                   (account_id, action_id, platform, entity_name, action_type, status, message, execution_time_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (action.get("account_id", 1),
                 action_id,
                 action.get("platform", ""),
                 action.get("entity_name", ""),
                 action.get("action_type", ""),
                 status,
                 message,
                 execution_time_ms)
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _is_in_cooldown(self, entity_name, action_type):
        """Check if entity had a recent executed action within cooldown period."""
        try:
            conn = get_connection()
            try:
                cutoff = (datetime.utcnow() - timedelta(
                    hours=self.config["cooldown_hours"]
                )).strftime("%Y-%m-%dT%H:%M:%SZ")
                row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM automation_actions
                       WHERE entity_name = ? AND action_type = ?
                       AND status = 'executed' AND executed_at >= ?""",
                    (entity_name, action_type, cutoff)
                ).fetchone()
                return (row["cnt"] if row else 0) > 0
            finally:
                conn.close()
        except Exception:
            return False

    def _notify(self, event, action):
        """Fire notification for automation event (non-blocking, errors swallowed)."""
        try:
            from app.services.notification_service import get_notification_service
            ns = get_notification_service()
            ns.send(event, {
                "action_id": action.get("id"),
                "action_type": action.get("action_type"),
                "entity_name": action.get("entity_name"),
                "platform": action.get("platform"),
                "account_id": action.get("account_id"),
                "confidence": action.get("confidence"),
                "reason": action.get("reason"),
            })
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # PROPOSAL SOURCES
    # ══════════════════════════════════════════════════════════

    def _proposals_from_budget(self, days, platform):
        """Generate budget increase proposals from scaling opportunities."""
        proposals = []
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            opps = bi.detect_scaling_opportunities(days, platform)
            for o in opps:
                proposals.append({
                    "action_type": "increase_budget",
                    "platform": "meta",
                    "entity_type": "campaign",
                    "entity_id": "",
                    "entity_name": o["campaign_name"],
                    "reason": o["reason"],
                    "confidence": o.get("confidence", "medium"),
                    "suggested_change_pct": o["suggested_budget_increase_pct"],
                })
        except Exception:
            pass
        return proposals

    def _proposals_from_waste(self, days, platform):
        """Generate pause proposals for wasting campaigns."""
        proposals = []
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            waste = bi.detect_budget_waste(days, platform)
            for c in waste.get("campaigns", []):
                proposals.append({
                    "action_type": "pause_campaign",
                    "platform": "meta",
                    "entity_type": "campaign",
                    "entity_id": "",
                    "entity_name": c.get("name", "Unknown"),
                    "reason": c.get("reason", "High spend with no results"),
                    "confidence": "high",
                    "suggested_change_pct": -100,
                })
        except Exception:
            pass
        return proposals

    def _proposals_from_creatives(self, days):
        """Generate creative rotation proposals from fatigue data."""
        proposals = []
        try:
            from app.services.creative_service import CreativeService
            cs = CreativeService()
            fatigued = cs.get_fatigued_creatives(days=days)
            for c in fatigued:
                action = "rotate_creative" if c.get("fatigue_status") == "critical" else "refresh_creative"
                proposals.append({
                    "action_type": action,
                    "platform": "meta",
                    "entity_type": "creative",
                    "entity_id": c.get("ad_id", ""),
                    "entity_name": c.get("name", "Unknown"),
                    "reason": f"Fatigue: {c.get('fatigue_status', 'unknown')}. Freq: {c.get('frequency', 0):.1f}",
                    "confidence": "high" if c.get("fatigue_status") == "critical" else "medium",
                    "suggested_change_pct": 0,
                })
        except Exception:
            pass
        return proposals

    def _proposals_from_anomalies(self, days):
        """Generate proposals from anomaly detection."""
        proposals = []
        try:
            from app.services.advanced_analytics_service import AdvancedAnalyticsService
            svc = AdvancedAnalyticsService()
            anomalies = svc.detect_metric_anomalies("cpa", days)
            for a in anomalies.get("anomalies", []):
                if a.get("direction") == "above" and a.get("severity") == "negative":
                    proposals.append({
                        "action_type": "decrease_budget",
                        "platform": "meta",
                        "entity_type": "account",
                        "entity_id": "",
                        "entity_name": "Account",
                        "reason": f"CPA anomaly detected: {a.get('message', 'CPA spike')}",
                        "confidence": "medium",
                        "suggested_change_pct": -10,
                    })
        except Exception:
            pass
        return proposals

    def _proposals_from_cross_platform(self, days):
        """Generate proposals from cross-platform insights."""
        proposals = []
        try:
            from app.services.cross_platform_service import CrossPlatformService
            cp = CrossPlatformService()
            opps = cp.detect_channel_opportunities(days)
            for opp in opps.get("opportunities", []):
                if opp.get("type") == "channel_efficiency":
                    from_p = opp.get("from_platform", "")
                    to_p = opp.get("to_platform", "")
                    proposals.append({
                        "action_type": "decrease_budget",
                        "platform": from_p,
                        "entity_type": "account",
                        "entity_id": "",
                        "entity_name": f"{from_p} account",
                        "reason": f"Rebalance: {to_p} shows better efficiency than {from_p}",
                        "confidence": opp.get("confidence", "medium"),
                        "suggested_change_pct": -10,
                    })
        except Exception:
            pass
        return proposals
