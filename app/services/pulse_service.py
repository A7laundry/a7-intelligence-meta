"""
PulseService — Persistent Performance Pulse tracking.

Manages fingerprinting, upsert, state transitions, and history
for the pulse_insights table.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from app.db.init_db import get_connection


class PulseService:
    # Auto-resolve insights not seen for this many days
    STALE_DAYS = 3

    # Promote new → persistent after this many days
    PERSIST_DAYS = 2

    # ------------------------------------------------------------------ #
    # Fingerprint
    # ------------------------------------------------------------------ #

    @staticmethod
    def fingerprint(account_id: int, rule_type: str) -> str:
        """Stable 16-char hex fingerprint for deduplication."""
        raw = f"{account_id}:{rule_type}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------ #
    # Upsert batch
    # ------------------------------------------------------------------ #

    @classmethod
    def upsert_insights(cls, account_id: int, insights: list) -> list:
        """
        Persist a list of freshly-generated insight dicts.

        Each insight must have at minimum:
            rule_type, signal, priority, title, body,
            metric, action_label, action_page

        Returns the same list enriched with:
            _db_id, _state, _occurrence_count, _days_active
        """
        now_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        seen_fps = set()

        conn = get_connection()
        try:
            enriched = []
            for ins in insights:
                rule_type = ins.get("rule_type", "unknown")
                fp = cls.fingerprint(account_id, rule_type)
                seen_fps.add(fp)

                row = conn.execute(
                    "SELECT * FROM pulse_insights WHERE account_id=? AND fingerprint=?",
                    (account_id, fp),
                ).fetchone()

                if row is None:
                    # First time we see this insight → INSERT
                    cur = conn.execute(
                        """
                        INSERT INTO pulse_insights
                            (account_id, fingerprint, rule_type, signal, priority,
                             title, body, metric, action_label, action_page,
                             state, first_seen_at, last_seen_at,
                             occurrence_count, history_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,'new',?,?,1,'[]')
                        """,
                        (
                            account_id, fp, rule_type,
                            ins.get("signal", "neutral"),
                            ins.get("priority", 5),
                            ins.get("title", ""),
                            ins.get("body", ""),
                            ins.get("metric"),
                            ins.get("action_label"),
                            ins.get("action_page"),
                            now_iso, now_iso,
                        ),
                    )
                    db_id = cur.lastrowid
                    state = "new"
                    occ = 1
                    days_active = 0
                else:
                    db_id = row["id"]
                    prev_state = row["state"]
                    first_seen = datetime.strptime(row["first_seen_at"][:19], "%Y-%m-%d %H:%M:%S")
                    days_active = (datetime.utcnow() - first_seen).days
                    new_occ = row["occurrence_count"] + 1

                    # State transitions
                    if prev_state == "resolved":
                        state = "recovered"
                    elif prev_state in ("new", "recovered") and days_active >= cls.PERSIST_DAYS:
                        state = "persistent"
                    else:
                        state = prev_state  # keep reviewed / persistent

                    # Append history entry
                    history = json.loads(row["history_json"] or "[]")
                    history.append({
                        "ts": now_iso,
                        "metric": ins.get("metric"),
                        "signal": ins.get("signal", "neutral"),
                    })
                    # Keep last 30 history entries
                    history = history[-30:]

                    conn.execute(
                        """
                        UPDATE pulse_insights
                           SET signal=?, priority=?, title=?, body=?,
                               metric=?, action_label=?, action_page=?,
                               state=?, last_seen_at=?,
                               occurrence_count=?, history_json=?,
                               resolved_at=NULL
                         WHERE id=?
                        """,
                        (
                            ins.get("signal", "neutral"),
                            ins.get("priority", 5),
                            ins.get("title", ""),
                            ins.get("body", ""),
                            ins.get("metric"),
                            ins.get("action_label"),
                            ins.get("action_page"),
                            state,
                            now_iso,
                            new_occ,
                            json.dumps(history),
                            db_id,
                        ),
                    )
                    occ = new_occ

                enriched.append({
                    **ins,
                    "_db_id": db_id,
                    "_state": state,
                    "_occurrence_count": occ,
                    "_days_active": days_active if row else 0,
                })

            # Auto-resolve stale insights (not in current batch)
            stale_cutoff = (
                datetime.utcnow() - timedelta(days=cls.STALE_DAYS)
            ).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                UPDATE pulse_insights
                   SET state='resolved', resolved_at=?
                 WHERE account_id=?
                   AND state NOT IN ('resolved')
                   AND last_seen_at < ?
                """,
                (now_iso, account_id, stale_cutoff),
            )

            conn.commit()
        finally:
            conn.close()

        return enriched

    # ------------------------------------------------------------------ #
    # State actions
    # ------------------------------------------------------------------ #

    @classmethod
    def mark_reviewed(cls, insight_id: int, account_id: int) -> bool:
        now_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        try:
            cur = conn.execute(
                """
                UPDATE pulse_insights
                   SET state='reviewed', reviewed_at=?
                 WHERE id=? AND account_id=?
                   AND state IN ('new','persistent','recovered')
                """,
                (now_iso, insight_id, account_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    @classmethod
    def mark_resolved(cls, insight_id: int, account_id: int) -> bool:
        now_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_connection()
        try:
            cur = conn.execute(
                """
                UPDATE pulse_insights
                   SET state='resolved', resolved_at=?
                 WHERE id=? AND account_id=?
                   AND state != 'resolved'
                """,
                (now_iso, insight_id, account_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # History
    # ------------------------------------------------------------------ #

    @classmethod
    def get_history(cls, insight_id: int, account_id: int) -> list:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT history_json FROM pulse_insights WHERE id=? AND account_id=?",
                (insight_id, account_id),
            ).fetchone()
            if row is None:
                return []
            return json.loads(row["history_json"] or "[]")
        finally:
            conn.close()
