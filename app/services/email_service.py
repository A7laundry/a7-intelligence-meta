"""Email notification service — SMTP or SendGrid."""
import os
import logging

logger = logging.getLogger(__name__)

# Config — set ONE of these:
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "noreply@a7intelligence.com")


def is_configured():
    return bool(SMTP_HOST or SENDGRID_API_KEY)


def send_email(to: str, subject: str, body_html: str, body_text: str = None) -> bool:
    """Send email via SendGrid or SMTP. Returns True on success."""
    if not is_configured():
        logger.debug("Email not configured — skipping send")
        return False

    try:
        if SENDGRID_API_KEY:
            return _send_sendgrid(to, subject, body_html, body_text)
        else:
            return _send_smtp(to, subject, body_html, body_text)
    except Exception as e:
        logger.exception(f"Email send failed to {to}: {e}")
        return False


def _send_sendgrid(to, subject, body_html, body_text):
    import requests
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        json={
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": EMAIL_FROM, "name": "A7 Intelligence"},
            "subject": subject,
            "content": [
                {"type": "text/html", "value": body_html},
            ] + ([{"type": "text/plain", "value": body_text}] if body_text else []),
        },
        timeout=15,
    )
    return resp.status_code == 202


def _send_smtp(to, subject, body_html, body_text):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to

    if body_text:
        msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        if SMTP_PORT == 587:
            server.starttls()
        if SMTP_USER and SMTP_PASS:
            server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, [to], msg.as_string())
    return True


def send_alert_email(to: str, alert: dict) -> bool:
    """Send a formatted alert notification email."""
    severity = alert.get("severity", "warning").upper()
    title = alert.get("title", "Alert")
    message = alert.get("message", "")
    account_name = alert.get("account_name", "Your account")

    color_map = {"CRITICAL": "#ff4444", "WARNING": "#ff9500", "INFO": "#4db8ff"}
    color = color_map.get(severity, "#ff9500")

    body_html = f"""
    <div style="font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:24px;border-radius:8px;max-width:600px">
      <h2 style="color:{color};margin:0 0 8px">{severity}: {title}</h2>
      <p style="color:#8b949e;margin:0 0 16px">{account_name}</p>
      <p style="margin:0 0 24px">{message}</p>
      <a href="#" style="background:{color};color:#000;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:700">
        View Dashboard
      </a>
      <p style="color:#30363d;margin-top:24px;font-size:12px">A7 Intelligence — Automated Alert</p>
    </div>
    """

    subject = f"[A7 Intelligence] {severity}: {title}"
    return send_email(to, subject, body_html, f"{severity}: {title}\n\n{message}")
