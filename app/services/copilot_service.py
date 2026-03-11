"""AI Marketing Copilot Service — Conversational intelligence layer.

Accepts natural language questions, gathers live system context with entity
references, calls an LLM provider, and returns structured answers that link
findings to actual campaigns, alerts, and creatives.

Response types:
  diagnosis   — why something happened
  risk        — threats and problems
  comparison  — period-over-period or platform comparisons
  opportunity — growth and scaling opportunities

Supported LLM providers (tried in order):
  1. Anthropic Claude  (ANTHROPIC_API_KEY)
  2. OpenAI / OpenRouter (OPENAI_API_KEY or OPENROUTER_API_KEY)
  3. Rule-based fallback (no key required)

Usage:
  svc = CopilotService()
  result = svc.ask("Why did CPA increase?", account_id=1, period="7d",
                   session_context=[{"question": "...", "answer": "...", "response_type": "..."}])
"""

import os
import json
from datetime import datetime

# Valid action types accepted by the Automation Engine
_VALID_ACTION_TYPES = {
    "pause_campaign", "increase_budget", "decrease_budget",
    "refresh_creative", "rotate_creative",
}

_DEFAULT_CHANGE_PCT = {
    "increase_budget": 20,
    "decrease_budget": -20,
    "pause_campaign": -100,
    "refresh_creative": 0,
    "rotate_creative": 0,
}


class CopilotService:
    """Conversational intelligence layer backed by live system data."""

    SYSTEM_PROMPT = """You are A7 Intelligence, an AI Marketing Copilot embedded in a performance marketing dashboard.

Live account data is provided in <context>. Answer ONLY based on that data. Do not invent numbers, campaigns, or trends not present in the context.

Classify your response as one of:
- diagnosis   → explains WHY something happened (why/what happened questions)
- risk        → identifies threats and problems (risk/alert/issue questions)
- comparison  → compares periods, campaigns, or platforms (vs/change/trend questions)
- opportunity → finds growth and optimization opportunities (scale/grow/budget questions)

For suggested_actions, set actionable=true ONLY when BOTH conditions hold:
1. action_type is exactly one of: pause_campaign, increase_budget, decrease_budget, refresh_creative, rotate_creative
2. entity_name is explicitly named in the context data (not a generic description)

For key_findings, include ref_type/ref_id/ref_name when a finding refers to a specific entity from context.
Supported ref_type values: campaign, alert, creative, account, metric

Respond with valid JSON only — no markdown fences, no extra text:
{
  "response_type": "diagnosis|risk|comparison|opportunity",
  "answer": "2-4 sentence answer. Use **bold** for key numbers and metric names.",
  "key_findings": [
    {"text": "finding text", "ref_type": "campaign|alert|creative|account|metric|null", "ref_id": "entity id from context or null", "ref_name": "exact name from context or null"}
  ],
  "suggested_actions": [
    {"text": "what to do", "actionable": true, "action_type": "pause_campaign|increase_budget|decrease_budget|refresh_creative|rotate_creative|null", "entity_name": "exact name from context or null", "entity_type": "campaign|creative|null", "platform": "meta|google", "confidence_for_action": "high|medium|low", "reason": "one-line rationale"}
  ],
  "follow_up_questions": ["natural follow-up 1", "natural follow-up 2", "natural follow-up 3"],
  "confidence": "high|medium|low",
  "confidence_reason": "brief explanation, e.g. 'high — 7 days of campaign data with clear CPA trend'",
  "sources": ["daily_snapshots", "alerts", "campaign_snapshots", "budget_intelligence", "growth_score"]
}"""

    def __init__(self):
        self._anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._openai_key = (os.environ.get("OPENAI_API_KEY", "")
                            or os.environ.get("OPENROUTER_API_KEY", ""))
        self._openrouter = bool(os.environ.get("OPENROUTER_API_KEY", ""))

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def ask(self, question, account_id=None, period="7d", session_context=None):
        """Answer a natural language marketing question grounded in live data.

        Args:
            question:        The user's question.
            account_id:      Scope to this account (None = all accounts).
            period:          today | 7d | 30d
            session_context: List of previous {question, response_type, answer} dicts
                             (last 2 used for continuity).

        Returns:
            dict with: response_type, answer, key_findings, suggested_actions,
                       follow_up_questions, confidence, confidence_reason, sources,
                       context_summary, provider, generated_at
        """
        days = self._period_to_days(period)
        ctx = self._gather_context(account_id, days)
        context_text = self._format_context(ctx)
        user_msg = self._build_user_message(question, context_text, session_context or [])

        raw = self._call_llm(user_msg, ctx=ctx)
        parsed = self._parse_response(raw)

        parsed["context_summary"] = {
            "account_id": account_id,
            "period": period,
            "spend": ctx.get("summary", {}).get("spend", 0),
            "conversions": ctx.get("summary", {}).get("conversions", 0),
            "active_alerts": ctx.get("active_alerts", 0),
            "growth_score": ctx.get("growth_score", 0),
        }
        parsed["generated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        return parsed

    def create_proposal(self, action_type, entity_name, entity_type="campaign",
                        account_id=None, reason="Copilot suggestion",
                        confidence="medium", platform="meta"):
        """Convert a Copilot suggested action into an Automation Engine proposal.

        Routes through AutomationEngine.queue_proposal() which runs full guardrail
        validation. Does NOT execute — creates 'proposed' status for human review.

        Returns:
            {"success": True, "action_id": int}  or
            {"success": False, "reason": str, "action_id": None}
        """
        if action_type not in _VALID_ACTION_TYPES:
            return {"success": False,
                    "reason": f"action_type '{action_type}' is not supported",
                    "action_id": None}

        from app.services.automation_engine import AutomationEngine
        engine = AutomationEngine()
        proposal = {
            "action_type": action_type,
            "platform": platform or "meta",
            "entity_type": entity_type or "campaign",
            "entity_id": "",
            "entity_name": entity_name,
            "reason": f"[Copilot] {reason}",
            "confidence": confidence or "medium",
            "suggested_change_pct": _DEFAULT_CHANGE_PCT.get(action_type, 0),
            "account_id": account_id or 1,
        }
        return engine.queue_proposal(proposal)

    # ══════════════════════════════════════════════════════════
    # CONTEXT GATHERING
    # ══════════════════════════════════════════════════════════

    def _gather_context(self, account_id, days):
        """Pull live data from all services, preserving entity IDs for reference linking."""
        ctx = {}

        # Dashboard summary + campaigns with IDs
        try:
            from app.services.dashboard_service import DashboardService
            ds = DashboardService()
            range_key = "today" if days <= 1 else ("7d" if days <= 7 else "30d")
            data = ds.get_dashboard_data(range_key, account_id=account_id)
            ctx["summary"] = data.get("summary", {}).get("total", {})
            ctx["comparison"] = data.get("comparison", {}).get("changes", {})
            ctx["meta_campaigns"] = data.get("meta_campaigns", [])
            ctx["google_campaigns"] = data.get("google_campaigns", [])
        except Exception:
            ctx["summary"] = {}
            ctx["meta_campaigns"] = []
            ctx["google_campaigns"] = []

        # Alerts with IDs
        try:
            from app.services.alerts_service import AlertsService
            svc = AlertsService()
            alerts = svc.get_alerts(resolved=False, account_id=account_id, limit=10)
            ctx["alerts"] = alerts
            ctx["active_alerts"] = len(alerts)
        except Exception:
            ctx["alerts"] = []
            ctx["active_alerts"] = 0

        # Growth score + signals
        try:
            from app.services.growth_score_service import GrowthScoreService
            gs = GrowthScoreService()
            score = gs.build_growth_score(days=days, account_id=account_id)
            ctx["growth_score"] = score.get("score", 0)
            ctx["growth_label"] = score.get("label", "unknown")
            ctx["growth_summary"] = score.get("summary", "")
            ctx["growth_signals"] = score.get("signals", [])
        except Exception:
            ctx["growth_score"] = 0
            ctx["growth_label"] = "unknown"
            ctx["growth_signals"] = []

        # Budget intelligence with named campaigns
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            eff = bi.compute_efficiency_score(days=days, account_id=account_id)
            waste = bi.detect_budget_waste(days=days, account_id=account_id)
            opps = bi.detect_scaling_opportunities(days=days, account_id=account_id)
            ctx["budget_efficiency_score"] = eff.get("score", 0)
            ctx["budget_waste"] = waste.get("campaigns", [])
            ctx["budget_scale"] = opps[:5]
        except Exception:
            ctx["budget_efficiency_score"] = 0
            ctx["budget_waste"] = []
            ctx["budget_scale"] = []

        # Creatives with fatigue data
        try:
            from app.services.creative_service import CreativeService
            cs = CreativeService()
            fatigued = cs.get_fatigued_creatives(days=days, account_id=account_id)
            ctx["fatigued_creatives"] = fatigued[:5]
        except Exception:
            ctx["fatigued_creatives"] = []

        # AI Coach recommendations
        try:
            from app.services.ai_coach_service import AICoachService
            coach = AICoachService()
            recs = coach.generate_recommendations(days=days, account_id=account_id)
            ctx["recommendations"] = recs[:5]
        except Exception:
            ctx["recommendations"] = []

        return ctx

    def _format_context(self, ctx):
        """Render context into a text block with entity IDs for reference linking."""
        summary = ctx.get("summary", {})
        comparison = ctx.get("comparison", {})

        lines = [
            "## Performance Summary",
            f"- Spend: ${summary.get('spend', 0):.2f}",
            f"- Impressions: {summary.get('impressions', 0):,}",
            f"- Clicks: {summary.get('clicks', 0):,}",
            f"- CTR: {summary.get('ctr', 0):.2f}%",
            f"- Conversions: {summary.get('conversions', 0)}",
            f"- CPA: ${summary.get('cpa', 0):.2f}",
            "",
            "## Period-over-Period Changes",
        ]
        for k, v in comparison.items():
            try:
                lines.append(f"- {k}: {float(v):+.1f}%")
            except (TypeError, ValueError):
                lines.append(f"- {k}: {v}")

        lines += [
            "",
            "## Growth Score",
            f"- Score: {ctx.get('growth_score', 0)}/100 ({ctx.get('growth_label', 'unknown')})",
            f"- Summary: {ctx.get('growth_summary', '')}",
        ]
        signals = ctx.get("growth_signals", [])
        if signals:
            sig_text = ", ".join(str(s.get("label", s)) for s in signals[:4])
            lines.append(f"- Signals: {sig_text}")

        lines += [
            "",
            "## Budget Intelligence",
            f"- Efficiency Score: {ctx.get('budget_efficiency_score', 0)}/100",
        ]
        for c in ctx.get("budget_waste", [])[:3]:
            name = c.get("name", "Unknown")
            spend = c.get("spend", 0)
            lines.append(f"- [WASTE] {name}: spend=${spend:.2f}, 0 conversions")
        for o in ctx.get("budget_scale", [])[:3]:
            name = o.get("campaign_name", "Unknown")
            pct = o.get("suggested_budget_increase_pct", 0)
            conf = o.get("confidence", "medium")
            lines.append(f"- [SCALE] {name}: +{pct}% budget suggested ({conf} confidence)")

        lines += ["", "## Active Alerts (with IDs)"]
        for a in ctx.get("alerts", [])[:8]:
            alert_id = a.get("id", "")
            sev = a.get("severity", "info").upper()
            title = a.get("title", "")
            msg = a.get("message", "")
            lines.append(f"- [id:{alert_id}] [{sev}] {title} — {msg}")

        lines += ["", "## AI Coach Recommendations"]
        for r in ctx.get("recommendations", []):
            sev = r.get("severity", "").upper()
            title = r.get("title", "")
            msg = r.get("message", "")
            lines.append(f"- [{sev}] {title}: {msg}")

        meta = ctx.get("meta_campaigns", [])
        if meta:
            lines += ["", "## Meta Campaigns (with identifiers for reference linking)"]
            for c in sorted(meta, key=lambda x: x.get("spend", 0), reverse=True)[:7]:
                cid = c.get("campaign_id", "")
                name = c.get("name", "?")
                spend = c.get("spend", 0)
                conv = c.get("conversions", 0)
                cpa = c.get("cpa", 0)
                status = c.get("status", "?")
                lines.append(
                    f"- [id:{cid}] {name}: spend=${spend:.2f} conv={conv} "
                    f"CPA=${cpa:.2f} status={status}"
                )

        google = ctx.get("google_campaigns", [])
        if google:
            lines += ["", "## Google Campaigns"]
            for c in sorted(google, key=lambda x: x.get("spend", 0), reverse=True)[:4]:
                name = c.get("name", "?")
                spend = c.get("spend", 0)
                conv = c.get("conversions", 0)
                lines.append(f"- {name}: spend=${spend:.2f} conv={conv}")

        fatigued = ctx.get("fatigued_creatives", [])
        if fatigued:
            lines += ["", "## Fatigued Creatives"]
            for cr in fatigued:
                cr_id = cr.get("id", "")
                name = cr.get("name", "?")
                freq = cr.get("frequency", 0)
                status = cr.get("fatigue_status", "?")
                lines.append(f"- [id:{cr_id}] {name}: frequency={freq:.1f} fatigue={status}")

        return "\n".join(lines)

    def _build_user_message(self, question, context_text, session_context):
        """Build the full user message with optional conversation history."""
        parts = [f"<context>\n{context_text}\n</context>"]

        if session_context:
            history_lines = ["<conversation_history>"]
            for entry in session_context[-2:]:
                history_lines.append(f"Q: {entry.get('question', '')}")
                history_lines.append(f"Type: {entry.get('response_type', 'unknown')}")
                prev_answer = entry.get("answer", "")
                if len(prev_answer) > 200:
                    prev_answer = prev_answer[:200] + "…"
                history_lines.append(f"A: {prev_answer}")
                history_lines.append("")
            history_lines.append("</conversation_history>")
            parts.append("\n".join(history_lines))

        parts.append(f"Question: {question}")
        return "\n\n".join(parts)

    # ══════════════════════════════════════════════════════════
    # LLM PROVIDERS
    # ══════════════════════════════════════════════════════════

    def _call_llm(self, user_msg, ctx=None):
        """Try providers in priority order; fall back to rule-based."""
        if self._anthropic_key:
            result = self._call_anthropic(user_msg)
            if result:
                return result

        if self._openai_key:
            result = self._call_openai(user_msg)
            if result:
                return result

        # Extract question from user_msg for rule-based fallback
        question = user_msg.split("Question:")[-1].strip()
        return self._rule_based_response(question, user_msg, ctx=ctx)

    def _call_anthropic(self, user_msg):
        """Call Claude API via anthropic SDK, then fall back to raw HTTP."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._anthropic_key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}]
            )
            return {"text": msg.content[0].text, "provider": "anthropic"}
        except ImportError:
            return self._call_anthropic_http(user_msg)
        except Exception:
            return None

    def _call_anthropic_http(self, user_msg):
        """Call Claude API via stdlib urllib — no SDK required."""
        try:
            import urllib.request
            payload = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 800,
                "system": self.SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_msg}]
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "x-api-key": self._anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
            return {"text": body["content"][0]["text"], "provider": "anthropic"}
        except Exception:
            return None

    def _call_openai(self, user_msg):
        """Call OpenAI or OpenRouter via stdlib urllib."""
        try:
            import urllib.request
            base = "https://openrouter.ai/api/v1" if self._openrouter else "https://api.openai.com/v1"
            model = "anthropic/claude-haiku-4-5" if self._openrouter else "gpt-4o-mini"
            payload = json.dumps({
                "model": model,
                "max_tokens": 800,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ]
            }).encode()
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._openai_key}",
                    "Content-Type": "application/json",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
            provider = "openrouter" if self._openrouter else "openai"
            return {"text": body["choices"][0]["message"]["content"], "provider": provider}
        except Exception:
            return None

    def _rule_based_response(self, question, context_text, ctx=None):
        """Deterministic fallback when no LLM key is configured.

        Produces the same structured JSON schema as the LLM, with actionable
        suggestions linked to actual entity names from the live context.
        """
        ctx = ctx or {}
        q = question.lower()
        lines = context_text.split("\n")

        def _extract(label):
            for line in lines:
                if label in line:
                    return line.split(":", 1)[-1].strip()
            return "N/A"

        spend = _extract("- Spend:")
        cpa = _extract("- CPA:")
        score = _extract("- Score:")
        eff = _extract("- Efficiency Score:")
        alerts_count = _extract("- Count:")

        waste_names = [c.get("name", "") for c in ctx.get("budget_waste", [])[:2]]
        scale_names = [o.get("campaign_name", "") for o in ctx.get("budget_scale", [])[:2]]
        fatigue_names = [cr.get("name", "") for cr in ctx.get("fatigued_creatives", [])[:2]]
        top_alerts = ctx.get("alerts", [])[:3]

        # Determine type and build response
        if any(k in q for k in ("cpa", "cost per", "why", "increase", "spike", "drop")):
            rtype = "diagnosis"
            answer = (f"CPA is currently **{cpa}** with a budget efficiency of **{eff}**. "
                      f"The growth score is **{score}** — "
                      + ("wasting campaigns are contributing to elevated CPA."
                         if waste_names else "no wasting campaigns detected."))
            findings = [
                {"text": f"CPA: {cpa}", "ref_type": "metric", "ref_id": None, "ref_name": "CPA"},
                {"text": f"Budget efficiency: {eff}", "ref_type": "metric", "ref_id": None, "ref_name": "Efficiency Score"},
            ]
            for c in ctx.get("budget_waste", [])[:2]:
                findings.append({"text": f"{c.get('name')} is wasting ${c.get('spend', 0):.2f} with 0 conversions",
                                  "ref_type": "campaign", "ref_id": None, "ref_name": c.get("name")})
            actions = []
            for name in waste_names:
                actions.append({"text": f"Pause {name} — spend with no conversions",
                                 "actionable": True, "action_type": "pause_campaign",
                                 "entity_name": name, "entity_type": "campaign",
                                 "platform": "meta", "confidence_for_action": "high",
                                 "reason": "Zero conversions with active spend"})
            follow_ups = ["Which campaigns have the worst CPA?",
                          "How did CPA compare vs last week?",
                          "What's the budget efficiency breakdown?"]

        elif any(k in q for k in ("scale", "grow", "opportunit", "budget", "increase budget")):
            rtype = "opportunity"
            answer = (f"Growth score is **{score}** with budget efficiency at **{eff}**. "
                      + (f"Top scaling opportunities: {', '.join(scale_names)}."
                         if scale_names else "No scaling opportunities identified with current data."))
            findings = [
                {"text": f"Growth score: {score}", "ref_type": "metric", "ref_id": None, "ref_name": "Growth Score"},
            ]
            for o in ctx.get("budget_scale", [])[:2]:
                pct = o.get("suggested_budget_increase_pct", 20)
                findings.append({"text": f"{o.get('campaign_name')} — +{pct}% budget suggested",
                                  "ref_type": "campaign", "ref_id": None, "ref_name": o.get("campaign_name")})
            actions = []
            for o in ctx.get("budget_scale", [])[:2]:
                name = o.get("campaign_name", "")
                pct = o.get("suggested_budget_increase_pct", 20)
                conf = o.get("confidence", "medium")
                actions.append({"text": f"Increase budget on {name} by {pct}%",
                                 "actionable": True, "action_type": "increase_budget",
                                 "entity_name": name, "entity_type": "campaign",
                                 "platform": "meta", "confidence_for_action": conf,
                                 "reason": f"Scaling opportunity: +{pct}% suggested"})
            follow_ups = ["What is the current CPA on top converters?",
                          "How much additional budget is needed?",
                          "Which creatives support scaling?"]

        elif any(k in q for k in ("alert", "risk", "problem", "issue", "warn")):
            rtype = "risk"
            answer = (f"There are **{alerts_count} active alerts** requiring attention. "
                      f"Budget efficiency is **{eff}**. "
                      + ("Review critical alerts immediately." if ctx.get("active_alerts", 0) > 0
                         else "System is currently operating normally."))
            findings = [
                {"text": f"Active alerts: {alerts_count}", "ref_type": "metric", "ref_id": None, "ref_name": "Alerts"},
            ]
            for a in top_alerts:
                findings.append({"text": f"[{a.get('severity','').upper()}] {a.get('title','')}",
                                  "ref_type": "alert", "ref_id": str(a.get("id", "")),
                                  "ref_name": a.get("title", "")})
            actions = [
                {"text": "Review and resolve critical alerts in the Alerts Center",
                 "actionable": False, "action_type": None, "entity_name": None,
                 "entity_type": None, "platform": None, "confidence_for_action": "high",
                 "reason": "Active alerts indicate performance degradation"},
            ]
            for name in waste_names:
                actions.append({"text": f"Pause {name} to stop budget waste",
                                 "actionable": True, "action_type": "pause_campaign",
                                 "entity_name": name, "entity_type": "campaign",
                                 "platform": "meta", "confidence_for_action": "high",
                                 "reason": "Budget waste detected"})
            follow_ups = ["What triggered these alerts?",
                          "Which campaigns are most at risk?",
                          "How has performance changed this week?"]

        elif any(k in q for k in ("creative", "fatigue", "ad", "banner")):
            rtype = "diagnosis"
            answer = (f"**{len(ctx.get('fatigued_creatives', []))} fatigued creatives** detected. "
                      f"Growth score is **{score}**. "
                      + (f"Creatives needing rotation: {', '.join(fatigue_names)}."
                         if fatigue_names else "No critically fatigued creatives at this time."))
            findings = []
            for cr in ctx.get("fatigued_creatives", [])[:3]:
                findings.append({"text": f"{cr.get('name')} — frequency {cr.get('frequency', 0):.1f} ({cr.get('fatigue_status', '?')})",
                                  "ref_type": "creative", "ref_id": str(cr.get("id", "")),
                                  "ref_name": cr.get("name", "")})
            actions = []
            for cr in ctx.get("fatigued_creatives", [])[:2]:
                atype = "rotate_creative" if cr.get("fatigue_status") == "critical" else "refresh_creative"
                actions.append({"text": f"{'Rotate' if atype == 'rotate_creative' else 'Refresh'} {cr.get('name')}",
                                 "actionable": True, "action_type": atype,
                                 "entity_name": cr.get("name", ""), "entity_type": "creative",
                                 "platform": "meta", "confidence_for_action": "high",
                                 "reason": f"Frequency {cr.get('frequency', 0):.1f} signals fatigue"})
            follow_ups = ["Which campaigns use these creatives?",
                          "What CTR are the fatigued creatives getting?",
                          "When should new creatives be launched?"]

        else:
            rtype = "comparison"
            answer = (f"Account overview: spend **{spend}**, CPA **{cpa}**, "
                      f"growth score **{score}**, active alerts **{alerts_count}**, "
                      f"budget efficiency **{eff}**.")
            findings = [
                {"text": f"Spend: {spend}", "ref_type": "metric", "ref_id": None, "ref_name": "Spend"},
                {"text": f"CPA: {cpa}", "ref_type": "metric", "ref_id": None, "ref_name": "CPA"},
                {"text": f"Growth score: {score}", "ref_type": "metric", "ref_id": None, "ref_name": "Growth Score"},
            ]
            actions = [
                {"text": "Review AI Coach recommendations for personalized insights",
                 "actionable": False, "action_type": None, "entity_name": None,
                 "entity_type": None, "platform": None, "confidence_for_action": "medium",
                 "reason": "Full performance context available"},
            ]
            follow_ups = ["Why did CPA change recently?",
                          "Which campaigns should be scaled?",
                          "What are the biggest risks right now?"]

        # Determine confidence based on data availability
        data_points = (
            (1 if ctx.get("summary", {}).get("spend", 0) > 0 else 0) +
            (1 if len(ctx.get("meta_campaigns", [])) > 0 else 0) +
            (1 if ctx.get("growth_score", 0) > 0 else 0) +
            (1 if ctx.get("budget_efficiency_score", 0) > 0 else 0)
        )
        if data_points >= 3:
            confidence, conf_reason = "high", "sufficient live data across spend, campaigns, and growth metrics"
        elif data_points >= 1:
            confidence, conf_reason = "medium", "partial data — some metrics missing or zero"
        else:
            confidence, conf_reason = "low", "no live data available — running in demo mode"

        return {
            "text": json.dumps({
                "response_type": rtype,
                "answer": answer,
                "key_findings": findings,
                "suggested_actions": actions,
                "follow_up_questions": follow_ups,
                "confidence": confidence,
                "confidence_reason": conf_reason,
                "sources": ["daily_snapshots", "alerts", "campaign_snapshots",
                             "budget_intelligence", "growth_score"],
            }),
            "provider": "rule_based",
        }

    # ══════════════════════════════════════════════════════════
    # RESPONSE PARSING
    # ══════════════════════════════════════════════════════════

    def _parse_response(self, raw):
        """Extract structured fields; handle malformed output gracefully.

        Normalises key_findings and suggested_actions to object arrays
        regardless of whether the LLM returned strings or objects.
        """
        provider = (raw or {}).get("provider", "unknown")
        text = (raw or {}).get("text", "")

        try:
            cleaned = text.strip()
            # Strip markdown code fences
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:])
                if cleaned.rstrip().endswith("```"):
                    cleaned = cleaned.rstrip()[:-3].rstrip()
            parsed = json.loads(cleaned)
        except Exception:
            parsed = {
                "response_type": "analysis",
                "answer": text or "Unable to generate a response. Check LLM configuration.",
                "key_findings": [],
                "suggested_actions": [],
                "follow_up_questions": [],
                "confidence": "low",
                "confidence_reason": "LLM response could not be parsed",
                "sources": [],
            }

        # Normalise key_findings: strings → objects
        parsed["key_findings"] = [
            f if isinstance(f, dict) else {"text": f, "ref_type": None, "ref_id": None, "ref_name": None}
            for f in parsed.get("key_findings", [])
        ]

        # Normalise suggested_actions: strings → objects
        parsed["suggested_actions"] = [
            a if isinstance(a, dict) else {
                "text": a, "actionable": False, "action_type": None,
                "entity_name": None, "entity_type": None, "platform": "meta",
                "confidence_for_action": "medium", "reason": "",
            }
            for a in parsed.get("suggested_actions", [])
        ]

        # Safety guard: actionable=true only for valid action_types with entity_name
        for action in parsed["suggested_actions"]:
            if action.get("actionable"):
                if (action.get("action_type") not in _VALID_ACTION_TYPES
                        or not action.get("entity_name")):
                    action["actionable"] = False

        parsed["provider"] = provider
        return parsed

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _period_to_days(period):
        return {"today": 1, "1d": 1, "7d": 7, "30d": 30}.get(period, 7)
