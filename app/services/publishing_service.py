"""Publishing Service — draft, schedule, and publish content posts."""

import json
from datetime import datetime, timezone, timedelta

from app.db.init_db import get_connection

# Exponential backoff delays (seconds): retry 1=1min, 2=5min, 3=15min
_RETRY_BACKOFF = [60, 300, 900]
_MAX_RETRIES   = 3


class PublishingService:
    """Manage the full lifecycle of content posts and publishing jobs."""

    VALID_POST_TYPES = ("image_post", "carousel", "story", "reel", "banner", "ad_creative")
    VALID_STATUSES   = ("draft", "scheduled", "publishing", "published", "failed", "archived")
    VALID_PLATFORMS  = (
        "instagram", "facebook", "facebook_page",
        "google_display", "tiktok", "linkedin", "pinterest",
    )
    VALID_JOB_TYPES    = ("publish_now", "schedule", "retry")
    VALID_JOB_STATUSES = (
        "queued", "scheduled", "uploading", "publishing",
        "running", "success", "failed", "retrying", "cancelled", "dead",
    )

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
        """Return a single content post by id, optionally enriched with latest job."""
        conn = get_connection()
        try:
            query = "SELECT * FROM content_posts WHERE id = ?"
            params = [int(post_id)]
            if account_id is not None:
                query += " AND account_id = ?"
                params.append(int(account_id))
            row = conn.execute(query, params).fetchone()
            if not row:
                return {"error": "Post not found"}
            post = dict(row)
            # Attach latest job info
            job_row = conn.execute(
                "SELECT * FROM publishing_jobs WHERE content_post_id=? ORDER BY created_at DESC LIMIT 1",
                (int(post_id),),
            ).fetchone()
            if job_row:
                post["latest_job"] = {
                    "id": job_row["id"],
                    "status": job_row["status"],
                    "retry_count": job_row["retry_count"] or 0,
                    "result_message": job_row["result_message"] or "",
                    "executed_at": job_row["executed_at"] or "",
                    "next_retry_at": job_row["next_retry_at"] or "",
                }
            return post
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

    def publish_post_now(self, post_id, account_id, existing_job_id=None):
        """Publish a post immediately using real connector when credentials available.

        existing_job_id: if provided, updates that job record instead of creating new.
        """
        post = self.get_post(post_id, account_id)
        if "error" in post:
            return post

        platform = post.get("platform_target", "instagram")

        # Load connector credentials
        connector_ctx = None
        try:
            from app.services.social_connector_service import SocialConnectorService
            conn_data = SocialConnectorService().get_connector(account_id, platform)
            if (conn_data and conn_data.get("status") == "connected"
                    and conn_data.get("access_token")):
                connector_ctx = conn_data
        except Exception:
            pass

        # Mark as publishing
        self.update_post_status(post_id, account_id, "publishing")

        # Create or update job
        if existing_job_id:
            job = {"id": existing_job_id}
            self._update_job(existing_job_id, status="publishing")
        else:
            job = self._create_job(
                account_id=int(account_id),
                post_id=int(post_id),
                platform_target=platform,
                job_type="publish_now" if not existing_job_id else "retry",
                status="publishing",
            )

        # Build payload including asset URL if available
        asset_url = self._get_asset_url(post.get("creative_asset_id"))
        payload = {
            "title":           post.get("title", ""),
            "caption":         post.get("caption", ""),
            "platform_target": platform,
            "post_type":       post.get("post_type", "image_post"),
            "asset_url":       asset_url,
        }

        # Invoke connector
        from app.services.publishing_connector_service import PublishingConnectorService
        connector = PublishingConnectorService()
        result = connector.publish(platform, payload, connector_ctx=connector_ctx)

        # Persist outcome
        executed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        job_id = job.get("id") if job else None
        current_retry = self._get_job_retry_count(job_id)

        dead_lettered = False
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
                if job_id:
                    conn.execute(
                        """UPDATE publishing_jobs
                           SET status='success', executed_at=?, result_message=?,
                               updated_at=datetime('now')
                           WHERE id=?""",
                        (executed_at, result.get("message", ""), job_id),
                    )
                conn.commit()
                self._track_usage(int(account_id), "post_published_real"
                                  if connector_ctx else "post_published")
            else:
                # Failure — decide retry vs permanent vs dead-letter
                err_msg = result.get("message", "Publish failed")
                is_cred_err = result.get("credential_error", False)

                if is_cred_err or current_retry >= _MAX_RETRIES:
                    # Dead-letter: max retries exhausted or credential error
                    dead_lettered = True
                    dead_msg = (
                        f"[dead-lettered at {executed_at}] {err_msg}"
                    )
                    conn.execute(
                        "UPDATE content_posts SET status='failed', updated_at=datetime('now') WHERE id=? AND account_id=?",
                        (int(post_id), int(account_id)),
                    )
                    if job_id:
                        conn.execute(
                            """UPDATE publishing_jobs
                               SET status='dead', executed_at=?, result_message=?,
                                   updated_at=datetime('now')
                               WHERE id=?""",
                            (executed_at, dead_msg, job_id),
                        )
                else:
                    # Schedule retry with backoff
                    next_retry = self._next_retry_at(current_retry)
                    conn.execute(
                        "UPDATE content_posts SET status='failed', updated_at=datetime('now') WHERE id=? AND account_id=?",
                        (int(post_id), int(account_id)),
                    )
                    if job_id:
                        conn.execute(
                            """UPDATE publishing_jobs
                               SET status='retrying', retry_count=?, next_retry_at=?,
                                   executed_at=?, result_message=?, updated_at=datetime('now')
                               WHERE id=?""",
                            (current_retry + 1, next_retry, executed_at, err_msg, job_id),
                        )
                    self._track_usage(int(account_id), "publish_retry")
                conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()

        return {
            "post":         self.get_post(post_id, account_id),
            "result":       result,
            "dead_lettered": dead_lettered,
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
        """Execute all scheduled/retrying jobs whose time has passed."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        conn = get_connection()
        try:
            query = """SELECT * FROM publishing_jobs
                       WHERE (
                           (status = 'scheduled'  AND scheduled_for  <= ?)
                           OR (status = 'retrying' AND next_retry_at  <= ?)
                       )"""
            params = [now, now]
            if account_id is not None:
                query += " AND account_id = ?"
                params.append(int(account_id))
            jobs = conn.execute(query, params).fetchall()
        finally:
            conn.close()

        executed = []
        dead_lettered = 0
        for job in jobs:
            # Optimistic lock: only claim the job if its status hasn't changed
            claim_conn = get_connection()
            try:
                claim_conn.execute(
                    """UPDATE publishing_jobs SET status = 'uploading', updated_at = ?
                       WHERE id = ? AND status IN ('queued', 'scheduled', 'retrying')""",
                    (now, job["id"]),
                )
                claimed = claim_conn.total_changes
                claim_conn.commit()
            except Exception:
                try:
                    claim_conn.rollback()
                except Exception:
                    pass
                claimed = 0
            finally:
                claim_conn.close()

            if not claimed:
                # Another worker already claimed this job — skip it
                continue

            try:
                result = self.publish_post_now(
                    post_id=job["content_post_id"],
                    account_id=job["account_id"],
                    existing_job_id=job["id"],
                )
                # Check if this run resulted in dead-lettering
                post_result = result.get("result", {})
                if post_result.get("dead_lettered"):
                    dead_lettered += 1
                executed.append({"job_id": job["id"], "result": result})
            except Exception as e:
                executed.append({"job_id": job["id"], "error": str(e)})

        return {"executed": len(executed), "jobs": executed, "dead_lettered": dead_lettered}

    # ── Caption Generator ─────────────────────────────────────────────────────

    def _default_caption(self, account_id, content_idea_id, platform_target):
        """Build a default caption from content idea + platform-specific CTA."""
        try:
            conn = get_connection()
            idea = conn.execute(
                "SELECT * FROM content_ideas WHERE id = ? AND account_id = ?",
                (int(content_idea_id), account_id),
            ).fetchone()
            conn.close()
            if not idea:
                return ""
            ctas = {
                "instagram": "👇 Drop a comment below!",
                "facebook":  "Share with someone who needs this!",
                "facebook_page": "Share with someone who needs this!",
                "tiktok":    "Follow for more tips! 🎯",
                "linkedin":  "What do you think? Let's connect.",
                "pinterest": "Save for later! 📌",
                "google_display": "",
            }
            parts = [idea["title"] or ""]
            if idea["description"] and idea["description"] != idea["title"]:
                parts.append(idea["description"])
            cta = ctas.get(platform_target, "")
            if cta:
                parts.append(cta)
            return "\n\n".join(p for p in parts if p)
        except Exception:
            return ""

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _create_job(self, account_id, post_id, platform_target, job_type,
                    status="queued", scheduled_for=None):
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO publishing_jobs
                   (account_id, content_post_id, platform_target, job_type, status,
                    scheduled_for, retry_count)
                   VALUES (?,?,?,?,?,?,0)""",
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

    def _update_job(self, job_id, status):
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE publishing_jobs SET status=?, updated_at=datetime('now') WHERE id=?",
                (status, job_id),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _get_job_retry_count(self, job_id):
        if not job_id:
            return 0
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT retry_count FROM publishing_jobs WHERE id=?", (job_id,)
            ).fetchone()
            return row["retry_count"] or 0 if row else 0
        except Exception:
            return 0
        finally:
            conn.close()

    def _get_post_platform(self, post_id):
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

    def _get_asset_url(self, creative_asset_id):
        """Fetch asset_url from creative_assets for the given asset id."""
        if not creative_asset_id:
            return ""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT asset_url FROM creative_assets WHERE id=?",
                (int(creative_asset_id),),
            ).fetchone()
            return row["asset_url"] or "" if row else ""
        except Exception:
            return ""
        finally:
            conn.close()

    @staticmethod
    def _next_retry_at(retry_count):
        """Return ISO timestamp for next retry based on exponential backoff."""
        delay = _RETRY_BACKOFF[retry_count] if retry_count < len(_RETRY_BACKOFF) else _RETRY_BACKOFF[-1]
        return (datetime.now(timezone.utc) + timedelta(seconds=delay)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

    # ── Webhook Ingestion ─────────────────────────────────────────────────────

    def ingest_webhook(self, post_id, external_post_id="", status="", metrics=None):
        """Process a provider webhook callback and update post/metrics. Idempotent."""
        conn = get_connection()
        try:
            post = conn.execute(
                "SELECT * FROM content_posts WHERE id=?", (int(post_id),)
            ).fetchone()
            if not post:
                return {"error": "Post not found"}

            updates = []
            params = []

            if external_post_id and not post["external_post_id"]:
                updates.append("external_post_id=?")
                params.append(external_post_id)

            if status:
                mapped = self._map_provider_status(status)
                if mapped and mapped != post["status"]:
                    updates.append("status=?")
                    params.append(mapped)
                    if mapped == "published":
                        updates.append("published_at=datetime('now')")

            if updates:
                updates.append("updated_at=datetime('now')")
                params.append(int(post_id))
                conn.execute(
                    f"UPDATE content_posts SET {', '.join(updates)} WHERE id=?",
                    params,
                )
                conn.commit()

            if metrics:
                self._ingest_webhook_metrics(
                    conn, int(post_id), post["account_id"], metrics
                )

            return {"success": True, "post_id": int(post_id), "ingested": True}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    @staticmethod
    def _map_provider_status(provider_status):
        """Map a provider status string to an internal content_posts status."""
        mapping = {
            "published": "published",
            "success": "published",
            "failed": "failed",
            "error": "failed",
            "pending": "scheduled",
            "processing": "publishing",
        }
        return mapping.get((provider_status or "").lower(), "")

    @staticmethod
    def _ingest_webhook_metrics(conn, post_id, account_id, metrics):
        """Upsert metrics from a webhook payload into content_metrics."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            existing = conn.execute(
                "SELECT id FROM content_metrics WHERE content_post_id=? AND metric_date=?",
                (post_id, today),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE content_metrics
                       SET impressions=?, reach=?, clicks=?, engagement=?,
                           likes=?, comments=?, shares=?, saves=?, ctr=?
                       WHERE content_post_id=? AND metric_date=?""",
                    (
                        metrics.get("impressions", 0), metrics.get("reach", 0),
                        metrics.get("clicks", 0), metrics.get("engagement", 0),
                        metrics.get("likes", 0), metrics.get("comments", 0),
                        metrics.get("shares", 0), metrics.get("saves", 0),
                        metrics.get("ctr", 0.0),
                        post_id, today,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO content_metrics
                       (account_id, content_post_id, metric_date,
                        impressions, reach, clicks, engagement,
                        likes, comments, shares, saves, ctr)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        account_id, post_id, today,
                        metrics.get("impressions", 0), metrics.get("reach", 0),
                        metrics.get("clicks", 0), metrics.get("engagement", 0),
                        metrics.get("likes", 0), metrics.get("comments", 0),
                        metrics.get("shares", 0), metrics.get("saves", 0),
                        metrics.get("ctr", 0.0),
                    ),
                )
            conn.commit()
        except Exception:
            pass

    @staticmethod
    def _track_usage(account_id, metric):
        try:
            from app.services.billing_service import BillingService
            BillingService().track_usage(metric)
        except Exception:
            pass
