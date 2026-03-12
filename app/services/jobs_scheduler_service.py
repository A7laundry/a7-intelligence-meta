"""Jobs Scheduler Service — automatic background cron jobs.

Runs inside the Flask process using stdlib threading (no APScheduler needed).
All jobs delegate to SchedulerService which already handles logging + error
handling.

Schedule (UTC):
  snapshot      — every 6 hours  (00:00, 06:00, 12:00, 18:00)
  alerts        — every 6 hours  (same cadence as snapshot)
  ai-refresh    — daily at 08:00
  daily-briefing— daily at 08:00 (combined with ai-refresh pass)
  end-of-day    — daily at 22:00
"""

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_thread = None
_start_lock = threading.Lock()
_started = False

# Check interval in seconds — wake up every minute to see if a job is due
_CHECK_INTERVAL = 60


# ── Schedule definition ────────────────────────────────────────────────────────

def _should_run_snapshot(now: datetime) -> bool:
    """Every 6 hours on the hour."""
    return now.minute == 0 and now.hour % 6 == 0


def _should_run_ai_refresh(now: datetime) -> bool:
    """Daily at 08:00 UTC."""
    return now.hour == 8 and now.minute == 0


def _should_run_alerts(now: datetime) -> bool:
    """Every 6 hours on the hour."""
    return now.minute == 0 and now.hour % 6 == 0


def _should_run_end_of_day(now: datetime) -> bool:
    """Daily at 22:00 UTC."""
    return now.hour == 22 and now.minute == 0


# ── Job runner ────────────────────────────────────────────────────────────────

def _run_jobs_pass():
    """Check which jobs are due and execute them."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    try:
        from app.services.scheduler_service import SchedulerService
        svc = SchedulerService()
    except Exception as e:
        logger.warning(f"[jobs-scheduler] Could not init SchedulerService: {e}")
        return

    if _should_run_snapshot(now):
        try:
            result = svc.run_snapshot_job()
            logger.info(f"[jobs-scheduler] snapshot → {result.get('message', '')}")
        except Exception as e:
            logger.warning(f"[jobs-scheduler] snapshot failed: {e}")

    if _should_run_alerts(now):
        try:
            result = svc.run_alert_refresh_job()
            logger.info(f"[jobs-scheduler] alerts → {result.get('message', '')}")
        except Exception as e:
            logger.warning(f"[jobs-scheduler] alerts failed: {e}")

    if _should_run_ai_refresh(now):
        try:
            result = svc.run_ai_refresh_job()
            logger.info(f"[jobs-scheduler] ai-refresh → {result.get('message', '')}")
        except Exception as e:
            logger.warning(f"[jobs-scheduler] ai-refresh failed: {e}")

        try:
            result = svc.run_daily_briefing_job()
            logger.info(f"[jobs-scheduler] daily-briefing → {result.get('message', '')}")
        except Exception as e:
            logger.warning(f"[jobs-scheduler] daily-briefing failed: {e}")

    if _should_run_end_of_day(now):
        try:
            result = svc.run_end_of_day_summary_job()
            logger.info(f"[jobs-scheduler] end-of-day → {result.get('message', '')}")
        except Exception as e:
            logger.warning(f"[jobs-scheduler] end-of-day failed: {e}")


def _startup_snapshot():
    """Run an initial snapshot on startup if no data exists for today."""
    try:
        from datetime import date
        from app.db.init_db import get_connection
        today = date.today().isoformat()
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM daily_snapshots WHERE date = ?", (today,)
            ).fetchone()
            has_data = row and row["n"] > 0
        finally:
            conn.close()

        if not has_data:
            from app.services.scheduler_service import SchedulerService
            result = SchedulerService().run_snapshot_job()
            logger.info(f"[jobs-scheduler] startup snapshot → {result.get('message', '')}")
    except Exception as e:
        logger.warning(f"[jobs-scheduler] startup snapshot failed: {e}")


def _loop():
    """Thread entry point."""
    # On startup: take a snapshot if no data exists for today
    _startup_snapshot()

    while not _stop_event.is_set():
        try:
            _run_jobs_pass()
        except Exception as e:
            logger.warning(f"[jobs-scheduler] unhandled error in pass: {e}")
        _stop_event.wait(_CHECK_INTERVAL)


# ── Public API ────────────────────────────────────────────────────────────────

def start_jobs_scheduler():
    """Start the background jobs scheduler thread (idempotent)."""
    global _thread, _started

    with _start_lock:
        if _started and _thread and _thread.is_alive():
            return

        _stop_event.clear()
        _thread = threading.Thread(
            target=_loop,
            name="a7-jobs-scheduler",
            daemon=True,
        )
        _thread.start()
        _started = True
        logger.info("[jobs-scheduler] started — snapshot@6h, ai-refresh@08UTC, alerts@6h, eod@22UTC")


def stop_jobs_scheduler():
    """Signal the jobs scheduler thread to stop."""
    global _thread, _started
    _stop_event.set()
    if _thread:
        _thread.join(timeout=5)
        _thread = None
    with _start_lock:
        _started = False
