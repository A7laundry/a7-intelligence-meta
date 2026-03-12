"""Scheduler Loop Service — background auto-publish loop (Phase 8G).

Runs a publishing pass every 60 seconds:
  1. Execute all due scheduled/retrying publishing jobs.
  2. Detect and resolve stuck jobs (in uploading/publishing > 10 min).
  3. Send failure notifications via NotificationService.
  4. Log each pass to operations_log.

Uses only stdlib threading — no APScheduler dependency.
"""

import json
import logging
import threading
from datetime import datetime, timezone, timedelta

from app.db.init_db import get_connection

logger = logging.getLogger(__name__)

_LOOP_INTERVAL_SECONDS = 60
_STUCK_THRESHOLD_MINUTES = 10

_stop_event = threading.Event()
_scheduler_thread = None
_status_lock = threading.Lock()
_start_lock = threading.Lock()
_scheduler_started = False
_status = {
    "running": False,
    "started_at": None,
    "last_run_at": None,
    "last_run_status": None,
    "jobs_executed": 0,
    "jobs_failed": 0,
    "stuck_resolved": 0,
    "dead_lettered": 0,
}


# ── Public API ────────────────────────────────────────────────────────────────


def get_scheduler_status():
    """Return a snapshot of the current scheduler state."""
    with _status_lock:
        return dict(_status)


def run_publishing_loop():
    """Execute one scheduler pass: run due jobs, detect stuck, notify, log."""
    from app.services.publishing_service import PublishingService

    svc = PublishingService()
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    # 1. Run all due scheduled/retrying jobs
    run_result = svc.run_due_jobs()
    executed = run_result.get("executed", 0)
    job_details = run_result.get("jobs", [])
    failed = sum(1 for j in job_details if "error" in j)
    dead_lettered = run_result.get("dead_lettered", 0)

    # 2. Detect and resolve stuck jobs
    stuck = _detect_and_resolve_stuck_jobs()

    # 3. Send notifications for failures and stuck jobs
    _notify_failures(job_details, stuck)

    # 4. Log this pass to operations_log
    _log_loop_run(run_ts, executed, failed, len(stuck), dead_lettered)

    with _status_lock:
        _status["last_run_at"] = run_ts
        _status["last_run_status"] = "success" if failed == 0 else "warning"
        _status["jobs_executed"] += executed
        _status["jobs_failed"] += failed
        _status["stuck_resolved"] += len(stuck)
        _status["dead_lettered"] += dead_lettered

    return {
        "run_at": run_ts,
        "executed": executed,
        "failed": failed,
        "stuck_resolved": len(stuck),
        "dead_lettered": dead_lettered,
    }


def start_publishing_scheduler(app=None):
    """Start the background publishing scheduler thread (idempotent)."""
    global _scheduler_thread, _scheduler_started

    with _start_lock:
        if _scheduler_started and _scheduler_thread and _scheduler_thread.is_alive():
            logger.warning(
                "start_publishing_scheduler called but scheduler is already running — ignoring."
            )
            return

        _stop_event.clear()

        with _status_lock:
            _status["running"] = True
            _status["started_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            name="a7-publishing-scheduler",
            daemon=True,
        )
        _scheduler_thread.start()
        _scheduler_started = True


def stop_publishing_scheduler():
    """Signal the scheduler thread to stop and wait for it to exit."""
    global _scheduler_thread, _scheduler_started

    _stop_event.set()

    with _status_lock:
        _status["running"] = False

    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
        if _scheduler_thread.is_alive():
            logger.warning(
                "Scheduler thread did not stop cleanly within 5 seconds."
            )
        _scheduler_thread = None

    with _start_lock:
        _scheduler_started = False


# ── Internal helpers ──────────────────────────────────────────────────────────


def _scheduler_loop():
    """Thread entry point: loop every LOOP_INTERVAL_SECONDS until stopped."""
    while not _stop_event.is_set():
        try:
            run_publishing_loop()
        except Exception:
            pass  # Never let exceptions kill the scheduler thread
        _stop_event.wait(_LOOP_INTERVAL_SECONDS)


def _detect_and_resolve_stuck_jobs():
    """Find jobs stuck in uploading/publishing for > _STUCK_THRESHOLD_MINUTES.

    Marks them as failed and transitions the corresponding posts to failed as
    well.  Returns the list of resolved job dicts.
    """
    threshold = (
        datetime.now(timezone.utc) - timedelta(minutes=_STUCK_THRESHOLD_MINUTES)
    ).strftime("%Y-%m-%dT%H:%M:%S")

    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM publishing_jobs
               WHERE status IN ('uploading', 'publishing')
               AND COALESCE(updated_at, created_at) < ?""",
            (threshold,),
        ).fetchall()
        stuck = [dict(r) for r in rows]
    except Exception:
        stuck = []
    finally:
        conn.close()

    if not stuck:
        return stuck

    conn = get_connection()
    try:
        stuck_ids = [j["id"] for j in stuck]
        placeholders = ",".join("?" * len(stuck_ids))
        conn.execute(
            f"""UPDATE publishing_jobs
                SET status='failed',
                    result_message='Stuck job auto-resolved by scheduler',
                    updated_at=datetime('now')
                WHERE id IN ({placeholders})""",
            stuck_ids,
        )
        for j in stuck:
            conn.execute(
                """UPDATE content_posts
                   SET status='failed', updated_at=datetime('now')
                   WHERE id=? AND status IN ('publishing', 'uploading')""",
                (j["content_post_id"],),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()

    return stuck


def _notify_failures(job_details, stuck_jobs):
    """Dispatch failure notifications via NotificationService (graceful)."""
    try:
        from app.services.notification_service import get_notification_service
        notif = get_notification_service()

        for j in job_details:
            if "error" in j:
                notif.send("action_failed", {
                    "action_type": "publish_failed",
                    "action_id": j.get("job_id"),
                    "entity_name": f"Publishing job #{j.get('job_id')}",
                    "reason": j.get("error", "Unknown error"),
                    "platform": "",
                })

        for j in stuck_jobs:
            notif.send("action_failed", {
                "action_type": "publish_stuck",
                "action_id": j.get("id"),
                "entity_name": f"Publishing job #{j.get('id')} (stuck)",
                "reason": (
                    f"Job stuck in '{j.get('status')}' state for"
                    f" >{_STUCK_THRESHOLD_MINUTES} minutes"
                ),
                "platform": j.get("platform_target", ""),
            })
    except Exception:
        pass  # Never let notification failures crash the scheduler


def _log_loop_run(run_ts, executed, failed, stuck_count, dead_lettered=0):
    """Log one scheduler pass to the operations_log table."""
    try:
        status = "success" if failed == 0 and stuck_count == 0 else "warning"
        message = (
            f"Publishing loop: {executed} executed, "
            f"{failed} failed, {stuck_count} stuck resolved, "
            f"{dead_lettered} dead-lettered"
        )
        payload = json.dumps({
            "executed": executed,
            "failed": failed,
            "stuck_resolved": stuck_count,
            "dead_lettered": dead_lettered,
        })
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO operations_log
                   (operation_type, status, message, payload_json, started_at, finished_at)
                   VALUES ('publishing_loop', ?, ?, ?, ?, ?)""",
                (status, message, payload, run_ts, run_ts),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
