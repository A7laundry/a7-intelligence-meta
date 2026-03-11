"""Automation Guardrails Service — Enforces safe limits on automated actions.

Default mode is dry_run. Actions are proposed but not executed.
Guardrails enforce budget change caps, cooldowns, confidence thresholds,
and campaign whitelists/blacklists.

TODO: Add manual approval workflow integration (Phase 3+)
TODO: Add live execution mode with confirmation (Phase 3+)
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import get_connection


class AutomationGuardrailsService:
    """Validates and filters automation actions through safety rules."""

    # ── Default guardrail configuration ──
    DEFAULT_CONFIG = {
        "execution_mode": "dry_run",          # dry_run | live_blocked | live
        "max_actions_per_run": 5,             # Max actions in single execution
        "max_budget_change_pct": 30,          # Max budget increase/decrease %
        "min_confidence": "medium",           # Minimum confidence: low | medium | high
        "cooldown_hours": 24,                 # Hours before same campaign can be acted on again
        "blacklisted_campaigns": [],          # Campaign names never touched
        "whitelisted_campaigns": [],          # If set, only these can be touched
    }

    CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

    def __init__(self):
        self.config = self._load_config()

    def _load_config(self):
        """Load guardrail config from environment or defaults."""
        config = dict(self.DEFAULT_CONFIG)
        # Override from environment if available
        if os.environ.get("AUTOMATION_MODE"):
            config["execution_mode"] = os.environ["AUTOMATION_MODE"]
        if os.environ.get("MAX_BUDGET_CHANGE_PCT"):
            config["max_budget_change_pct"] = int(os.environ["MAX_BUDGET_CHANGE_PCT"])
        if os.environ.get("MAX_ACTIONS_PER_RUN"):
            config["max_actions_per_run"] = int(os.environ["MAX_ACTIONS_PER_RUN"])
        return config

    def get_guardrails_config(self):
        """Return current effective guardrails configuration."""
        return {
            **self.config,
            "guardrails_active": True,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def generate_proposals(self, days=7, platform=None):
        """Generate automation action proposals from intelligence data."""
        proposals = []

        # Budget scaling proposals
        proposals.extend(self._generate_budget_proposals(days, platform))

        # Creative proposals
        proposals.extend(self._generate_creative_proposals(days))

        # Waste/pause proposals
        proposals.extend(self._generate_waste_proposals(days, platform))

        return proposals

    def apply_guardrails(self, proposals, mode=None):
        """Validate proposals through guardrails and return filtered result."""
        effective_mode = mode or self.config["execution_mode"]
        allowed = []
        blocked = []

        for p in proposals[:self.config["max_actions_per_run"]]:
            result = self.validate_action(p)
            if result["allowed"]:
                p["blocked_by_guardrail"] = False
                p["guardrail_reason"] = None
                p["execution_mode"] = effective_mode
                allowed.append(p)
            else:
                p["blocked_by_guardrail"] = True
                p["guardrail_reason"] = result["reason"]
                p["execution_mode"] = "blocked"
                blocked.append(p)

        # Extra proposals beyond limit are blocked
        for p in proposals[self.config["max_actions_per_run"]:]:
            p["blocked_by_guardrail"] = True
            p["guardrail_reason"] = f"Exceeds max {self.config['max_actions_per_run']} actions per run"
            p["execution_mode"] = "blocked"
            blocked.append(p)

        return {
            "allowed": allowed,
            "blocked": blocked,
            "execution_mode": effective_mode,
            "total_proposals": len(proposals),
            "allowed_count": len(allowed),
            "blocked_count": len(blocked),
            "guardrails": self.config,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def validate_action(self, action):
        """Validate a single action against all guardrail rules."""
        entity_name = action.get("entity_name", "")

        # Rule 1: Blacklist check
        if entity_name in self.config["blacklisted_campaigns"]:
            return {"allowed": False, "reason": f"Campaign '{entity_name}' is blacklisted"}

        # Rule 2: Whitelist check (if whitelist is set, only those are allowed)
        if self.config["whitelisted_campaigns"] and entity_name not in self.config["whitelisted_campaigns"]:
            return {"allowed": False, "reason": f"Campaign '{entity_name}' not in whitelist"}

        # Rule 3: Budget change cap
        change_pct = abs(action.get("suggested_change_pct", 0))
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

    def _is_in_cooldown(self, entity_name, action_type):
        """Check if entity had a recent action within cooldown period."""
        try:
            conn = get_connection()
            try:
                cutoff = (datetime.utcnow() - timedelta(hours=self.config["cooldown_hours"])).strftime("%Y-%m-%dT%H:%M:%SZ")
                row = conn.execute(
                    """SELECT COUNT(*) as cnt FROM operations_log
                       WHERE message LIKE ? AND created_at >= ?""",
                    (f"%{entity_name}%", cutoff)
                ).fetchone()
                return (row["cnt"] if row else 0) > 0
            finally:
                conn.close()
        except Exception:
            return False

    # ── Proposal Generators ──

    def _generate_budget_proposals(self, days, platform):
        """Generate budget scaling proposals."""
        proposals = []
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            opps = bi.detect_scaling_opportunities(days, platform)

            for o in opps:
                proposals.append({
                    "action_type": "increase_budget",
                    "entity_type": "campaign",
                    "entity_name": o["campaign_name"],
                    "reason": o["reason"],
                    "confidence": o.get("confidence", "medium"),
                    "suggested_change_pct": o["suggested_budget_increase_pct"],
                    "metrics": o.get("metrics", {}),
                })
        except Exception:
            pass
        return proposals

    def _generate_creative_proposals(self, days):
        """Generate creative rotation/review proposals."""
        proposals = []
        try:
            from app.services.creative_service import CreativeService
            cs = CreativeService()
            fatigued = cs.get_fatigued_creatives(days=days)

            for c in fatigued:
                action = "rotate_creative" if c.get("fatigue_status") == "critical" else "review_creative"
                proposals.append({
                    "action_type": action,
                    "entity_type": "creative",
                    "entity_name": c.get("name", "Unknown"),
                    "reason": f"Fatigue status: {c.get('fatigue_status', 'unknown')}. Frequency: {c.get('frequency', 0):.1f}",
                    "confidence": "high" if c.get("fatigue_status") == "critical" else "medium",
                    "suggested_change_pct": 0,
                    "metrics": {"score": c.get("score", 0), "frequency": c.get("frequency", 0)},
                })
        except Exception:
            pass
        return proposals

    def _generate_waste_proposals(self, days, platform):
        """Generate pause proposals for waste campaigns."""
        proposals = []
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            waste = bi.detect_budget_waste(days, platform)

            for c in waste.get("campaigns", []):
                proposals.append({
                    "action_type": "pause_campaign",
                    "entity_type": "campaign",
                    "entity_name": c.get("name", "Unknown"),
                    "reason": c.get("reason", "High spend with no results"),
                    "confidence": "high",
                    "suggested_change_pct": -100,
                    "metrics": {"spend": c.get("spend", 0)},
                })
        except Exception:
            pass
        return proposals
