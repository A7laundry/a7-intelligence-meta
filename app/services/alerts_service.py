"""Alerts Service — Generates, deduplicates, persists and dispatches operational alerts.

Supports alert types: waste_spend, scaling_opportunity, budget_spike,
creative_fatigue, efficiency_decline, snapshot_failure.

Alerts are stored in SQLite with deduplication by (alert_type, entity_name, date).
Optional Slack webhook delivery when SLACK_WEBHOOK_URL is configured.

TODO: Add email delivery channel (Phase 3+)
TODO: Add auto-resolve logic for recovered conditions (Phase 3+)
TODO: Add alert escalation for persistent unresolved alerts (Phase 3+)
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.init_db import get_connection


class AlertsService:
    """Manages alert lifecycle: creation, deduplication, persistence, delivery."""

    SEVERITY_ORDER = {"critical": 0, "warning": 1, "success": 2, "info": 3}

    def __init__(self):
        self.webhook_url = None
        self._init_webhook()

    def _init_webhook(self):
        """Load Slack webhook URL from config or environment."""
        self.webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            try:
                from config import ALERT_CONFIG
                self.webhook_url = ALERT_CONFIG.get("slack_webhook_url")
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════
    # ALERT GENERATION
    # ══════════════════════════════════════════════════════════

    def generate_all_alerts(self, days=7, account_id=1):
        """Run all alert checks and return new alerts."""
        alerts = []
        alerts.extend(self._check_waste_alerts(days))
        alerts.extend(self._check_scaling_alerts(days))
        alerts.extend(self._check_budget_spike_alerts(days))
        alerts.extend(self._check_creative_fatigue_alerts(days))
        alerts.extend(self._check_efficiency_decline_alerts(days))

        # Tag all alerts with account_id
        for a in alerts:
            a["account_id"] = account_id

        # Deduplicate, persist, and optionally deliver
        new_alerts = []
        for alert in alerts:
            if not self._is_duplicate(alert):
                alert_id = self._persist(alert)
                alert["id"] = alert_id
                new_alerts.append(alert)
                self._deliver(alert)

        # Sort by severity
        new_alerts.sort(key=lambda a: self.SEVERITY_ORDER.get(a.get("severity", "info"), 4))
        return new_alerts

    def get_active_alerts(self, limit=50, severity=None, account_id=None):
        """Get recent alerts from database."""
        conn = get_connection()
        try:
            query = "SELECT * FROM alerts WHERE resolved = 0"
            params = []
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            if account_id is not None:
                query += " AND account_id = ?"
                params.append(account_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def get_alert_history(self, days=7, limit=100, account_id=None):
        """Get alert history for a period."""
        conn = get_connection()
        try:
            from datetime import timedelta
            since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            query = "SELECT * FROM alerts WHERE created_at >= ?"
            params = [since]
            if account_id is not None:
                query += " AND account_id = ?"
                params.append(account_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def resolve_alert(self, alert_id):
        """Mark an alert as resolved."""
        conn = get_connection()
        try:
            conn.execute("UPDATE alerts SET resolved = 1 WHERE id = ?", (alert_id,))
            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # ALERT CHECKS
    # ══════════════════════════════════════════════════════════

    def _check_waste_alerts(self, days):
        """Check for campaigns wasting budget."""
        alerts = []
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            waste = bi.detect_budget_waste(days)
            for c in waste.get("campaigns", []):
                alerts.append(self._make_alert(
                    alert_type="waste_spend",
                    severity="critical",
                    entity_type="campaign",
                    entity_name=c.get("name", ""),
                    title=f"Budget waste: {c.get('name', '')}",
                    message=c.get("reason", f"${c.get('spend', 0):.2f} spent with no results"),
                    payload={"spend": c.get("spend", 0), "conversions": c.get("conversions", 0)},
                ))
        except Exception:
            pass
        return alerts

    def _check_scaling_alerts(self, days):
        """Check for scaling opportunities."""
        alerts = []
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            opps = bi.detect_scaling_opportunities(days)
            for o in opps[:3]:  # Top 3 only
                alerts.append(self._make_alert(
                    alert_type="scaling_opportunity",
                    severity="success",
                    entity_type="campaign",
                    entity_name=o["campaign_name"],
                    title=f"Scale opportunity: {o['campaign_name']}",
                    message=f"{o['reason']}. Suggested increase: {o['suggested_budget_increase_pct']}%.",
                    payload=o["metrics"],
                ))
        except Exception:
            pass
        return alerts

    def _check_budget_spike_alerts(self, days):
        """Check for budget anomalies."""
        alerts = []
        try:
            from app.services.budget_intelligence_service import BudgetIntelligenceService
            bi = BudgetIntelligenceService()
            result = bi.detect_spend_anomalies(days)
            for a in result.get("anomalies", []):
                if a["type"] == "spend_spike":
                    alerts.append(self._make_alert(
                        alert_type="budget_spike",
                        severity="warning",
                        entity_type="account",
                        entity_name=f"Day {a['date']}",
                        title=f"Spend spike on {a['date']}",
                        message=a["message"],
                        payload=a.get("metrics", {}),
                    ))
        except Exception:
            pass
        return alerts

    def _check_creative_fatigue_alerts(self, days):
        """Check for critical creative fatigue."""
        alerts = []
        try:
            from app.services.creative_service import CreativeService
            cs = CreativeService()
            fatigued = cs.get_fatigued_creatives(days=days)
            for c in fatigued:
                if c.get("fatigue_status") in ("critical", "fatigued"):
                    alerts.append(self._make_alert(
                        alert_type="creative_fatigue",
                        severity="warning",
                        entity_type="creative",
                        entity_name=c.get("name", ""),
                        title=f"Creative fatigue: {c.get('name', '')}",
                        message=f"Fatigue status: {c['fatigue_status']}. Frequency: {c.get('frequency', 0):.1f}.",
                        payload={"score": c.get("score", 0), "frequency": c.get("frequency", 0)},
                    ))
        except Exception:
            pass
        return alerts

    def _check_efficiency_decline_alerts(self, days):
        """Check for CPA/efficiency deterioration."""
        alerts = []
        try:
            from app.services.dashboard_service import DashboardService
            ds = DashboardService()
            range_key = "7d" if days <= 7 else "30d"
            data = ds.get_dashboard_data(range_key)
            changes = data.get("comparison", {}).get("changes", {})

            conv_change = changes.get("conversions", 0)
            spend_change = changes.get("spend", 0)

            if spend_change > 15 and conv_change < -10:
                alerts.append(self._make_alert(
                    alert_type="efficiency_decline",
                    severity="warning",
                    entity_type="account",
                    entity_name="Account",
                    title="Efficiency declining",
                    message=f"Spend up {spend_change:.0f}% while conversions down {abs(conv_change):.0f}%.",
                    payload={"spend_change": spend_change, "conv_change": conv_change},
                ))
        except Exception:
            pass
        return alerts

    # ══════════════════════════════════════════════════════════
    # PERSISTENCE & DEDUPLICATION
    # ══════════════════════════════════════════════════════════

    def _is_duplicate(self, alert):
        """Check if an identical alert was already created today."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT id FROM alerts
                   WHERE alert_type = ? AND entity_name = ? AND date(created_at) = ?""",
                (alert["alert_type"], alert.get("entity_name", ""), today)
            ).fetchone()
            return row is not None
        except Exception:
            return False
        finally:
            conn.close()

    def _persist(self, alert):
        """Save alert to database, return ID."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO alerts
                   (account_id, alert_type, severity, entity_type, entity_name, title, message,
                    payload_json, platform)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (alert.get("account_id", 1),
                 alert["alert_type"], alert["severity"],
                 alert.get("entity_type", ""), alert.get("entity_name", ""),
                 alert["title"], alert["message"],
                 json.dumps(alert.get("payload", {})),
                 alert.get("platform")),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception:
            return None
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # DELIVERY
    # ══════════════════════════════════════════════════════════

    def _deliver(self, alert):
        """Deliver alert via configured channels."""
        if self.webhook_url:
            self._send_slack(alert)

    def _send_slack(self, alert):
        """Send alert to Slack webhook."""
        try:
            import requests
            severity_emoji = {
                "critical": ":rotating_light:",
                "warning": ":warning:",
                "success": ":white_check_mark:",
                "info": ":information_source:",
            }
            emoji = severity_emoji.get(alert["severity"], ":bell:")
            payload = {
                "text": f"{emoji} *{alert['title']}*\n{alert['message']}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{emoji} *{alert['title']}*\n{alert['message']}"
                        }
                    }
                ]
            }
            requests.post(self.webhook_url, json=payload, timeout=10)
        except Exception:
            pass  # Graceful failure — alerts still persist even if webhook fails

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _make_alert(alert_type, severity, entity_type, entity_name, title, message, payload=None):
        return {
            "alert_type": alert_type,
            "severity": severity,
            "entity_type": entity_type,
            "entity_name": entity_name,
            "title": title,
            "message": message,
            "payload": payload or {},
            "platform": "meta",
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    @staticmethod
    def _row_to_dict(row):
        d = dict(row)
        if "payload_json" in d:
            try:
                d["payload"] = json.loads(d["payload_json"])
            except Exception:
                d["payload"] = {}
            del d["payload_json"]
        return d
