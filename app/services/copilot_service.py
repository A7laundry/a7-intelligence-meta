"""AI Marketing Copilot Service — Conversational intelligence layer.

Accepts natural language questions, gathers live system context,
calls an LLM provider, and returns structured answers grounded in real data.

Supported LLM providers (tried in order):
  1. Anthropic Claude (ANTHROPIC_API_KEY)
  2. OpenAI / OpenRouter (OPENAI_API_KEY or OPENROUTER_API_KEY)
  3. Rule-based fallback (no key required)

Usage:
  from app.services.copilot_service import CopilotService
  svc = CopilotService()
  result = svc.ask("Why did CPA increase yesterday?", account_id=1, period="7d")
"""

import os
import json
from datetime import datetime


class CopilotService:
    """Conversational intelligence layer backed by live system data."""

    SYSTEM_PROMPT = """You are A7 Intelligence, an AI Marketing Copilot embedded in a performance marketing platform.

You have access to real data from the user's ad accounts including spend, conversions, CPA, CTR, campaign performance, budget efficiency, alerts, and growth scores. This data is provided in the <context> block below.

Your job is to answer the user's marketing question accurately, concisely, and based ONLY on the provided context. Do not invent numbers or trends that are not present in the context.

Respond in JSON with this exact structure:
{
  "answer": "<markdown-formatted answer, 2-4 sentences>",
  "key_findings": ["<finding 1>", "<finding 2>"],
  "suggested_actions": ["<action 1>", "<action 2>"],
  "confidence": "high|medium|low",
  "sources": ["<source 1>", "<source 2>"]
}

Rules:
- If the context does not contain enough data to answer, say so clearly and set confidence to "low".
- Keep the answer focused and actionable.
- Suggested actions must be concrete and tied to the data.
- Sources are the data tables/metrics you used (e.g. "campaign_snapshots", "alerts", "growth_score").
"""

    def __init__(self):
        self._anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._openai_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OPENROUTER_API_KEY", "")
        self._openrouter = bool(os.environ.get("OPENROUTER_API_KEY", ""))

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def ask(self, question, account_id=None, period="7d"):
        """Answer a natural language marketing question grounded in live data.

        Returns:
            dict: {
                answer, key_findings, suggested_actions, confidence,
                sources, context_summary, provider, generated_at
            }
        """
        days = self._period_to_days(period)
        context = self._gather_context(account_id, days)
        context_text = self._format_context(context)

        raw = self._call_llm(question, context_text)
        parsed = self._parse_response(raw)

        parsed["context_summary"] = {
            "account_id": account_id,
            "period": period,
            "spend": context.get("summary", {}).get("spend", 0),
            "conversions": context.get("summary", {}).get("conversions", 0),
            "active_alerts": context.get("active_alerts", 0),
            "growth_score": context.get("growth_score", 0),
        }
        parsed["generated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        return parsed

    # ══════════════════════════════════════════════════════════
    # CONTEXT GATHERING
    # ══════════════════════════════════════════════════════════

    def _gather_context(self, account_id, days):
        """Pull live data from all relevant services."""
        ctx = {}

        # Dashboard summary
        try:
            from app.services.dashboard_service import DashboardService
            ds = DashboardService()
            range_key = "today" if days <= 1 else ("7d" if days <= 7 else "30d")
            data = ds.get_dashboard_data(range_key, account_id=account_id)
            summary = data.get("summary", {}).get("total", {})
            ctx["summary"] = summary
            ctx["comparison"] = data.get("comparison", {}).get("changes", {})
            ctx["meta_campaigns"] = data.get("meta_campaigns", [])
            ctx["google_campaigns"] = data.get("google_campaigns", [])
        except Exception:
            ctx["summary"] = {}
            ctx["meta_campaigns"] = []
            ctx["google_campaigns"] = []

        # Alerts
        try:
            from app.services.alerts_service import AlertsService
            svc = AlertsService()
            alerts = svc.get_alerts(resolved=False, account_id=account_id, limit=10)
            ctx["alerts"] = alerts
            ctx["active_alerts"] = len(alerts)
        except Exception:
            ctx["alerts"] = []
            ctx["active_alerts"] = 0

        # Growth score
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

        # Budget intelligence
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            eff = bi.compute_efficiency_score(days=days, account_id=account_id)
            waste = bi.detect_budget_waste(days=days, account_id=account_id)
            opps = bi.detect_scaling_opportunities(days=days, account_id=account_id)
            ctx["budget_efficiency_score"] = eff.get("score", 0)
            ctx["budget_waste_campaigns"] = [c.get("name", "") for c in waste.get("campaigns", [])]
            ctx["budget_scale_campaigns"] = [o.get("campaign_name", "") for o in opps[:3]]
        except Exception:
            ctx["budget_efficiency_score"] = 0
            ctx["budget_waste_campaigns"] = []
            ctx["budget_scale_campaigns"] = []

        # AI Coach recommendations (top 5)
        try:
            from app.services.ai_coach_service import AICoachService
            coach = AICoachService()
            recs = coach.generate_recommendations(days=days, account_id=account_id)
            ctx["recommendations"] = [
                {"title": r.get("title", ""), "severity": r.get("severity", ""),
                 "message": r.get("message", "")}
                for r in recs[:5]
            ]
        except Exception:
            ctx["recommendations"] = []

        return ctx

    def _format_context(self, ctx):
        """Render the context dict into a concise text block for the LLM prompt."""
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
            lines.append(f"- {k}: {v:+.1f}%")

        lines += [
            "",
            "## Growth Score",
            f"- Score: {ctx.get('growth_score', 0)}/100 ({ctx.get('growth_label', 'unknown')})",
            f"- Summary: {ctx.get('growth_summary', '')}",
        ]

        signals = ctx.get("growth_signals", [])
        if signals:
            lines.append("- Signals: " + ", ".join(str(s.get("label", s)) for s in signals[:4]))

        lines += [
            "",
            "## Budget Intelligence",
            f"- Efficiency Score: {ctx.get('budget_efficiency_score', 0)}/100",
        ]
        if ctx.get("budget_waste_campaigns"):
            lines.append("- Wasting campaigns: " + ", ".join(ctx["budget_waste_campaigns"][:3]))
        if ctx.get("budget_scale_campaigns"):
            lines.append("- Scale opportunities: " + ", ".join(ctx["budget_scale_campaigns"]))

        lines += ["", "## Active Alerts", f"- Count: {ctx.get('active_alerts', 0)}"]
        for a in ctx.get("alerts", [])[:5]:
            lines.append(f"  - [{a.get('severity','info').upper()}] {a.get('title','')} — {a.get('message','')}")

        lines += ["", "## AI Coach Recommendations"]
        for r in ctx.get("recommendations", []):
            lines.append(f"- [{r.get('severity','').upper()}] {r.get('title','')}: {r.get('message','')}")

        meta = ctx.get("meta_campaigns", [])
        if meta:
            lines += ["", "## Top Meta Campaigns"]
            for c in sorted(meta, key=lambda x: x.get("spend", 0), reverse=True)[:5]:
                lines.append(
                    f"- {c.get('name','?')}: spend=${c.get('spend',0):.2f} "
                    f"conv={c.get('conversions',0)} CPA=${c.get('cpa',0):.2f} status={c.get('status','?')}"
                )

        return "\n".join(lines)

    # ══════════════════════════════════════════════════════════
    # LLM PROVIDERS
    # ══════════════════════════════════════════════════════════

    def _call_llm(self, question, context_text):
        """Try providers in priority order; fall back to rule-based response."""
        if self._anthropic_key:
            result = self._call_anthropic(question, context_text)
            if result:
                return result

        if self._openai_key:
            result = self._call_openai(question, context_text)
            if result:
                return result

        return self._rule_based_response(question, context_text)

    def _call_anthropic(self, question, context_text):
        """Call Claude API via anthropic SDK or raw HTTP."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._anthropic_key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                system=self.SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"<context>\n{context_text}\n</context>\n\nQuestion: {question}"
                }]
            )
            return {"text": msg.content[0].text, "provider": "anthropic"}
        except ImportError:
            return self._call_anthropic_http(question, context_text)
        except Exception:
            return None

    def _call_anthropic_http(self, question, context_text):
        """Call Claude API via raw urllib (no SDK required)."""
        try:
            import urllib.request
            payload = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 512,
                "system": self.SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": f"<context>\n{context_text}\n</context>\n\nQuestion: {question}"
                }]
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

    def _call_openai(self, question, context_text):
        """Call OpenAI or OpenRouter via raw HTTP (no SDK required)."""
        try:
            import urllib.request
            base = "https://openrouter.ai/api/v1" if self._openrouter else "https://api.openai.com/v1"
            model = "anthropic/claude-haiku-4-5" if self._openrouter else "gpt-4o-mini"
            payload = json.dumps({
                "model": model,
                "max_tokens": 512,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": f"<context>\n{context_text}\n</context>\n\nQuestion: {question}"}
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

    def _rule_based_response(self, question, context_text):
        """Deterministic fallback when no LLM key is configured."""
        q = question.lower()
        lines = context_text.split("\n")

        def _extract(label):
            for l in lines:
                if label in l:
                    return l.split(":", 1)[-1].strip()
            return "N/A"

        spend = _extract("- Spend:")
        cpa = _extract("- CPA:")
        score = _extract("- Score:")
        eff = _extract("- Efficiency Score:")
        alerts = _extract("- Count:")

        if any(k in q for k in ("cpa", "cost per")):
            answer = f"CPA is currently {cpa}. Budget efficiency is {eff}. Review the campaigns section for waste and anomalies."
            findings = [f"CPA: {cpa}", f"Budget efficiency: {eff}"]
            actions = ["Review wasting campaigns", "Check budget anomalies"]
        elif any(k in q for k in ("scale", "increase", "grow")):
            answer = f"Growth score is {score}. Efficiency is {eff}. Check the scale opportunities list in Budget Intelligence."
            findings = [f"Growth score: {score}", f"Efficiency: {eff}"]
            actions = ["Scale campaigns flagged as opportunities", "Increase budget by 15-20% on top converters"]
        elif any(k in q for k in ("alert", "risk", "issue", "problem")):
            answer = f"There are {alerts} active alerts. Review the Alerts Center for details."
            findings = [f"Active alerts: {alerts}"]
            actions = ["Review and resolve active alerts", "Check critical severity alerts first"]
        elif any(k in q for k in ("spend", "budget", "waste")):
            answer = f"Total spend is {spend}. Budget efficiency score is {eff}. Check for wasting campaigns in Budget Intelligence."
            findings = [f"Total spend: {spend}", f"Efficiency: {eff}"]
            actions = ["Pause wasting campaigns", "Reallocate budget to top performers"]
        else:
            answer = f"Account performance: spend={spend}, CPA={cpa}, growth score={score}, active alerts={alerts}, budget efficiency={eff}."
            findings = [f"Spend: {spend}", f"Growth score: {score}"]
            actions = ["Review AI Coach recommendations", "Check active alerts"]

        return {
            "text": json.dumps({
                "answer": answer,
                "key_findings": findings,
                "suggested_actions": actions,
                "confidence": "medium",
                "sources": ["daily_snapshots", "alerts", "growth_score_service", "budget_intelligence_service"]
            }),
            "provider": "rule_based"
        }

    # ══════════════════════════════════════════════════════════
    # RESPONSE PARSING
    # ══════════════════════════════════════════════════════════

    def _parse_response(self, raw):
        """Extract structured fields from LLM response; gracefully handle malformed output."""
        provider = raw.get("provider", "unknown") if raw else "unknown"
        text = raw.get("text", "") if raw else ""

        try:
            # Strip markdown code fences if present
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:])
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()
            parsed = json.loads(cleaned)
        except Exception:
            # Best-effort: return text as-is
            parsed = {
                "answer": text or "Unable to generate a response. Please check LLM configuration.",
                "key_findings": [],
                "suggested_actions": [],
                "confidence": "low",
                "sources": [],
            }

        parsed["provider"] = provider
        return parsed

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _period_to_days(period):
        mapping = {"today": 1, "1d": 1, "7d": 7, "30d": 30}
        return mapping.get(period, 7)
