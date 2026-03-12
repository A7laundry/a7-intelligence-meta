"""Publishing Service — draft, schedule, and publish content posts."""

import json
from datetime import datetime, timezone

from app.db.init_db import get_connection


class PublishingService:
    """Manage the full lifecycle of content posts and publishing jobs."""

    VALID_POST_TYPES = ("image_post", "carousel", "story", "reel", "banner", "ad_creative")
    VALID_STATUSES = ("draft", "scheduled", "publishing", "published", "failed", "archived")
    VALID_PLATFORMS = (
        "instagram", "facebook", "google_display", "tiktok", "linkedin", "pinterest"
    )
    VALID_JOB_TYPES = ("publish_now", "schedule", "retry")
    VALID_JOB_STATUSES = ("queued", "scheduled", "running", "success", "failed", "cancelled")

    # ── Content Posts ─────────────────────────────────────────────────────────

    def create_post(self, account_id, content_idea_id=None, creative_asset_id=None,
                    title="", caption="", platform_target="instagram",
                    post_type="image_post"):
        """Insert a new content post draft and return its record."""
        if post_type not in self.VALID_POST_TYPES:
            post_type = "image_post"
        if platform_target not in self.VALID_PLATFORMS:
            platform_target = "instagram"
        account_id = int(account_id)

        # Generate default caption when empty
        if not caption and content_idea_id:
            caption = self._default_caption(account_id, content_idea_id, platform_target)

        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO content_posts
                   (account_id, content_idea_id, creative_asset_id, title, caption,
                    platform_target, post_type, status)
                   VALUES (?,?,?,?,?,?,?,'draft')""",
                (account_id, content_idea_id, creative_asset_id,
                 title, caption, platform_target, post_type),
            )
            conn.commit()
            post_id = cur.lastrowid
            self._track_usage(account_id, "post_created")
            return self.get_post(post_id, account_id)
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def list_posts(self, account_id=None, status=None, platform_target=None, limit=100):
        """Return content posts, optionally filtered."""
        conn = get_connection()
        try:
            query = "SELECT * FROM content_posts"
            params = []
            conditions = []
            if account_id is not None:
                conditions.append("account_id = ?")
                params.append(int(account_id))
            if status and status in self.VALID_STATUSES:
                conditions.append("status = ?")
                params.append(status)
            if platform_target and platform_target in self.VALID_PLATFORMS:
                conditions.append("platform_target = ?")
                params.append(platform_target)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY COALESCE(scheduled_for, created_at) DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def get_post(self, post_id, account_id=None):
        """Return a single content post by id."""
        conn = get_connection()
        try:
            query = "SELECT * FROM content_posts WHERE id = ?"
            params = [int(post_id)]
            if account_id is not None:
                query += " AND account_id = ?"
                params.append(int(account_id))
            row = conn.execute(query, params).fetchone()
            if row:
                return dict(row)
            return {"error": "Post not found"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def update_post_status(self, post_id, account_id, status):
        """Transition a post to a new status."""
        if status not in self.VALID_STATUSES:
            return {"error": f"Invalid status: {status}"}
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE content_posts SET status=?, updated_at=datetime('now') WHERE id=? AND account_id=?",
                (status, int(post_id), int(account_id)),
            )
            conn.commit()
            return {"success": True, "post_id": int(post_id), "status": status}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def schedule_post(self, post_id, account_id, scheduled_for):
        """Set a post as scheduled for a future datetime."""
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE content_posts
                   SET status='scheduled', scheduled_for=?, updated_at=datetime('now')
                   WHERE id=? AND account_id=?""",
                (scheduled_for, int(post_id), int(account_id)),
            )
            conn.commit()
            # Create a scheduling job
            self._create_job(
                account_id=int(account_id),
                post_id=int(post_id),
                platform_target=self._get_post_platform(post_id),
                job_type="schedule",
                status="scheduled",
                scheduled_for=scheduled_for,
            )
            self._track_usage(int(account_id), "post_scheduled")
            return self.get_post(post_id, account_id)
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def publish_post_now(self, post_id, account_id):
        """Publish a post immediately using the configured connector."""
        post = self.get_post(post_id, account_id)
        if "error" in post:
            return post

        # Mark as publishing
        self.update_post_status(post_id, account_id, "publishing")

        # Create job
        job = self._create_job(
            account_id=int(account_id),
            post_id=int(post_id),
            platform_target=post.get("platform_target", "instagram"),
            job_type="publish_now",
            status="running",
        )

        # Invoke connector
        from app.services.publishing_connector_service import PublishingConnectorService
        connector = PublishingConnectorService()
        payload = {
            "title": post.get("title", ""),
            "caption": post.get("caption", ""),
            "platform_target": post.get("platform_target", "instagram"),
            "post_type": post.get("post_type", "image_post"),
        }
        result = connector.publish(post.get("platform_target", "instagram"), payload)

        # Update post and job based on result
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        conn = get_connection()
        try:
            if result.get("success"):
                conn.execute(
                    """UPDATE content_posts
                       SET status='published', published_at=?, external_post_id=?,
                           updated_at=datetime('now')
                       WHERE id=? AND account_id=?""",
                    (executed_at, result.get("external_post_id", ""),
                     int(post_id), int(account_id)),
                )
                job_status = "success"
            else:
                conn.execute(
                    "UPDATE content_posts SET status='failed', updated_at=datetime('now') WHERE id=? AND account_id=?",
                    (int(post_id), int(account_id)),
                )
                job_status = "failed"

            # Update job
            if job and "id" in job:
                conn.execute(
                    """UPDATE publishing_jobs
                       SET status=?, executed_at=?, result_message=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (job_status, executed_at, result.get("message", ""), job["id"]),
                )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

        if result.get("success"):
            self._track_usage(int(account_id), "post_published")

        return {
            "post": self.get_post(post_id, account_id),
            "result": result,
        }

    # ── Publishing Jobs ───────────────────────────────────────────────────────

    def list_jobs(self, account_id=None, status=None, limit=100):
        """Return publishing jobs, optionally filtered."""
        conn = get_connection()
        try:
            query = "SELECT * FROM publishing_jobs"
            params = []
            conditions = []
            if account_id is not None:
                conditions.append("account_id = ?")
                params.append(int(account_id))
            if status and status in self.VALID_JOB_STATUSES:
                conditions.append("status = ?")
                params.append(status)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def run_due_jobs(self, account_id=None):
        """Execute all scheduled jobs whose scheduled_for time has passed."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        conn = get_connection()
        try:
            query = """SELECT j.*, p.account_id as post_account_id
                       FROM publishing_jobs j
                       LEFT JOIN content_posts p ON j.content_post_id = p.id
                       WHERE j.status = 'scheduled' AND j.scheduled_for <= ?"""
            params = [now]
            if account_id is not None:
                query += " AND j.account_id = ?"
                params.append(int(account_id))
            jobs = conn.execute(query, params).fetchall()
        finally:
            conn.close()

        executed = []
        for job in jobs:
            try:
                result = self.publish_post_now(
                    post_id=job["content_post_id"],
                    account_id=job["account_id"],
                )
                executed.append({"job_id": job["id"], "result": result})
            except Exception as e:
                executed.append({"job_id": job["id"], "error": str(e)})

        return {"executed": len(executed), "jobs": executed}

    # ── Caption Generator ─────────────────────────────────────────────────────

    def _default_caption(self, account_id, content_idea_id, platform_target):
        """Build a default caption from content idea + brand kit."""
        try:
            conn = get_connection()
            idea = conn.execute(
                "SELECT * FROM content_ideas WHERE id = ? AND account_id = ?",
                (int(content_idea_id), account_id),
            ).fetchone()
            conn.close()
            if not idea:
                return ""

            desc = idea["description"] or ""
            title = idea["title"] or ""

            # Platform-specific CTA
            ctas = {
                "instagram": "👇 Drop a comment below!",
                "facebook": "Share with someone who needs this!",
                "tiktok": "Follow for more tips! 🎯",
                "linkedin": "What do you think? Let's connect.",
                "google_display": "",
                "pinterest": "Save for later! 📌",
            }
            cta = ctas.get(platform_target, "")

            parts = [title]
            if desc and desc != title:
                parts.append(desc)
            if cta:
                parts.append(cta)
            return "\n\n".join(parts)
        except Exception:
            return ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _create_job(self, account_id, post_id, platform_target, job_type,
                    status="queued", scheduled_for=None):
        """Insert a publishing_jobs row and return it."""
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO publishing_jobs
                   (account_id, content_post_id, platform_target, job_type, status, scheduled_for)
                   VALUES (?,?,?,?,?,?)""",
                (account_id, post_id, platform_target, job_type, status, scheduled_for),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM publishing_jobs WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row) if row else {"id": cur.lastrowid}
        except Exception:
            return {}
        finally:
            conn.close()

    def _get_post_platform(self, post_id):
        """Return the platform_target of a post."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT platform_target FROM content_posts WHERE id = ?", (int(post_id),)
            ).fetchone()
            return row["platform_target"] if row else "instagram"
        except Exception:
            return "instagram"
        finally:
            conn.close()

    @staticmethod
    def _track_usage(account_id, metric):
        """Increment usage_metrics for billing consistency."""
        try:
            from app.services.billing_service import BillingService
            BillingService().track_usage(metric)
        except Exception:
            pass
