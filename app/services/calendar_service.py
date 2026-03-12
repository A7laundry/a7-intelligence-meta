"""Content Calendar service — editorial calendar layer over content_posts."""

import calendar as cal_mod
from datetime import datetime, timedelta

from app.db.init_db import get_connection


def _parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _date_range(start, count):
    return [start + timedelta(days=i) for i in range(count)]


class CalendarService:
    # ------------------------------------------------------------------
    # Calendar view
    # ------------------------------------------------------------------

    def get_calendar(self, account_id, view="week", start=None):
        """Group content_posts into calendar cells.

        view  : "day" | "week" | "month"
        start : "YYYY-MM-DD" string (defaults to today / start-of-week / start-of-month)

        Returns dict:
          view, start, end, total_posts, days[]
          Each day: date, label, day_num, weekday, is_today, posts[]
        """
        today = datetime.utcnow().date()
        if start:
            try:
                start_date = _parse_date(start)
            except ValueError:
                start_date = today
        else:
            start_date = today

        if view == "day":
            dates = [start_date]
        elif view == "month":
            first = start_date.replace(day=1)
            _, days_in_month = cal_mod.monthrange(first.year, first.month)
            dates = _date_range(first, days_in_month)
            start_date = first
        else:  # week (default)
            monday = start_date - timedelta(days=start_date.weekday())
            dates = _date_range(monday, 7)
            start_date = monday

        end_date = dates[-1]
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d") + "T23:59:59"

        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT p.id, p.account_id, p.title, p.caption,
                       p.platform_target, p.post_type, p.status,
                       p.scheduled_for, p.published_at, p.external_post_id,
                       p.creative_asset_id,
                       ca.thumbnail_url, ca.asset_url
                FROM content_posts p
                LEFT JOIN creative_assets ca ON ca.id = p.creative_asset_id
                WHERE p.account_id = ?
                  AND (
                    (p.status IN ('scheduled','publishing','failed','retrying')
                     AND p.scheduled_for BETWEEN ? AND ?)
                    OR (p.status = 'published'
                        AND p.published_at BETWEEN ? AND ?)
                    OR (p.status = 'draft'
                        AND p.scheduled_for IS NOT NULL
                        AND p.scheduled_for BETWEEN ? AND ?)
                  )
                ORDER BY COALESCE(p.scheduled_for, p.published_at) ASC
                """,
                (
                    int(account_id),
                    start_str, end_str,
                    start_str, end_str,
                    start_str, end_str,
                ),
            ).fetchall()
        finally:
            conn.close()

        posts = [dict(r) for r in rows]

        def _post_date(p):
            ts = (
                p.get("published_at")
                if p["status"] == "published"
                else p.get("scheduled_for")
            )
            if ts:
                try:
                    return datetime.fromisoformat(ts.replace("Z", "")).date()
                except Exception:
                    pass
            return None

        date_map = {d: [] for d in dates}
        for p in posts:
            d = _post_date(p)
            if d and d in date_map:
                date_map[d].append(p)

        days = []
        for d in dates:
            days.append(
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "label": d.strftime("%a"),
                    "day_num": d.day,
                    "weekday": d.weekday(),
                    "is_today": d == today,
                    "posts": date_map[d],
                }
            )

        return {
            "view": view,
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "days": days,
            "total_posts": len(posts),
        }

    # ------------------------------------------------------------------
    # Reschedule
    # ------------------------------------------------------------------

    def reschedule_post(self, account_id, post_id, scheduled_for):
        """Reschedule a post to a new datetime.

        Rules:
        - Published posts cannot be rescheduled (duplicate instead).
        - Publishing-in-progress posts cannot be rescheduled.
        - Updates content_posts.scheduled_for and status → 'scheduled'.
        - Updates any pending publishing_jobs (queued/scheduled/retrying).

        Returns {"post": {...}} or {"error": "..."}.
        """
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM content_posts WHERE id=? AND account_id=?",
                (int(post_id), int(account_id)),
            ).fetchone()
            if not row:
                return {"error": "Post not found"}
            post = dict(row)

            if post["status"] == "published":
                return {
                    "error": "Cannot reschedule a published post. Duplicate it instead."
                }
            if post["status"] == "publishing":
                return {"error": "Post is currently being published"}

            try:
                datetime.fromisoformat(scheduled_for.replace("Z", ""))
            except (ValueError, AttributeError):
                return {"error": "Invalid scheduled_for format. Use ISO 8601."}

            conn.execute(
                """UPDATE content_posts
                   SET scheduled_for=?, status='scheduled', updated_at=datetime('now')
                   WHERE id=? AND account_id=?""",
                (scheduled_for, int(post_id), int(account_id)),
            )
            conn.execute(
                """UPDATE publishing_jobs
                   SET scheduled_for=?, updated_at=datetime('now')
                   WHERE content_post_id=? AND status IN ('queued','scheduled','retrying')""",
                (scheduled_for, int(post_id)),
            )
            conn.commit()

            updated = conn.execute(
                "SELECT * FROM content_posts WHERE id=?", (int(post_id),)
            ).fetchone()
            return {"post": dict(updated)}
        except Exception as e:
            conn.rollback()
            return {"error": str(e)}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Upcoming queue
    # ------------------------------------------------------------------

    def get_upcoming(self, account_id, limit=50):
        """Return next N scheduled posts ordered by scheduled_for ASC."""
        conn = get_connection()
        try:
            now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            rows = conn.execute(
                """
                SELECT p.id, p.account_id, p.title, p.caption,
                       p.platform_target, p.post_type, p.status,
                       p.scheduled_for, p.published_at,
                       p.creative_asset_id, ca.thumbnail_url
                FROM content_posts p
                LEFT JOIN creative_assets ca ON ca.id = p.creative_asset_id
                WHERE p.account_id = ?
                  AND p.status IN ('scheduled', 'publishing')
                  AND p.scheduled_for >= ?
                ORDER BY p.scheduled_for ASC
                LIMIT ?
                """,
                (int(account_id), now, int(limit)),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
