"""Notification Service — Multi-channel event dispatch for automation events.

Supports Slack webhook, Email (SMTP), and generic webhook channels.
All channels are configured from environment variables.
No third-party dependencies — uses only stdlib urllib.request and smtplib.

Supported events: action_proposed, action_approved, action_executed, action_failed
"""

import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from urllib import request as urllib_request
from urllib.error import URLError


_SUPPORTED_EVENTS = {
    "action_proposed",
    "action_approved",
    "action_executed",
    "action_failed",
}


def _build_summary(event, payload):
    """Build a human-readable summary string for the given event and payload."""
    action_type = payload.get("action_type", "unknown")
    entity = payload.get("entity_name", "unknown")
    platform = payload.get("platform", "")
    confidence = payload.get("confidence", "")
    reason = payload.get("reason", "")
    action_id = payload.get("action_id", "")

    parts = [f"[A7 Automation] {event.upper()}"]
    if action_id:
        parts.append(f"Action #{action_id}")
    parts.append(f"Type: {action_type}")
    parts.append(f"Entity: {entity}")
    if platform:
        parts.append(f"Platform: {platform}")
    if confidence:
        parts.append(f"Confidence: {confidence}")
    if reason:
        parts.append(f"Reason: {reason}")

    return " | ".join(parts)


class NotificationService:
    """Dispatches automation events to all configured notification channels.

    Channels are enabled by the presence of their respective environment variables.
    Failures in individual channels are logged to stderr and silently ignored.
    """

    def __init__(self):
        self._slack_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
        self._webhook_url = os.environ.get("NOTIFICATION_WEBHOOK_URL", "").strip()
        self._smtp_host = os.environ.get("SMTP_HOST", "").strip()
        self._smtp_port = int(os.environ.get("SMTP_PORT", "587") or "587")
        self._smtp_user = os.environ.get("SMTP_USER", "").strip()
        self._smtp_password = os.environ.get("SMTP_PASSWORD", "").strip()
        self._email_to_raw = os.environ.get("NOTIFICATION_EMAIL_TO", "").strip()

    # ── Public API ──────────────────────────────────────────────────────────

    def send(self, event, payload):
        """Dispatch notification for the given event to all enabled channels.

        Args:
            event (str): One of action_proposed, action_approved,
                         action_executed, action_failed.
            payload (dict): Action details to include in the notification.
        """
        summary = _build_summary(event, payload)

        if self._slack_url:
            self._send_slack(summary)

        if self._webhook_url:
            self._send_webhook(event, payload)

        if self._smtp_host and self._smtp_user and self._email_to_raw:
            self._send_email(event, summary)

    # ── Slack ────────────────────────────────────────────────────────────────

    def _send_slack(self, summary):
        """POST a JSON message to the configured Slack incoming webhook."""
        try:
            body = json.dumps({"text": summary}).encode("utf-8")
            req = urllib_request.Request(
                self._slack_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=10) as resp:
                _ = resp.read()
        except (URLError, OSError, Exception) as exc:
            print(f"[notification_service] Slack send failed: {exc}", file=sys.stderr)

    # ── Generic Webhook ──────────────────────────────────────────────────────

    def _send_webhook(self, event, payload):
        """POST event + payload as JSON to the configured generic webhook URL."""
        try:
            body = json.dumps({"event": event, "payload": payload}).encode("utf-8")
            req = urllib_request.Request(
                self._webhook_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=10) as resp:
                _ = resp.read()
        except (URLError, OSError, Exception) as exc:
            print(f"[notification_service] Webhook send failed: {exc}", file=sys.stderr)

    # ── Email (SMTP) ─────────────────────────────────────────────────────────

    def _send_email(self, event, summary):
        """Send a plain-text email via SMTP with TLS (STARTTLS on port 587)."""
        try:
            recipients = [r.strip() for r in self._email_to_raw.split(",") if r.strip()]
            if not recipients:
                return

            subject = f"[A7 Automation] {event}"
            msg = MIMEText(summary, "plain")
            msg["Subject"] = subject
            msg["From"] = self._smtp_user
            msg["To"] = ", ".join(recipients)

            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self._smtp_user, self._smtp_password)
                server.sendmail(self._smtp_user, recipients, msg.as_string())
        except Exception as exc:
            print(f"[notification_service] Email send failed: {exc}", file=sys.stderr)


# ── Singleton factory ─────────────────────────────────────────────────────────

_instance = None


def get_notification_service():
    """Return the module-level singleton NotificationService instance."""
    global _instance
    if _instance is None:
        _instance = NotificationService()
    return _instance
