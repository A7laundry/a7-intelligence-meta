"""Social Connector Service — account-scoped social publishing credentials."""

from app.db.init_db import get_connection


class SocialConnectorService:
    """CRUD and validation for social publishing connectors."""

    VALID_PLATFORMS = ("instagram", "facebook_page")
    VALID_STATUSES = ("connected", "invalid", "expired", "disconnected")

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save_connector(self, account_id, platform, access_token="",
                       page_id="", ig_user_id="", status="disconnected"):
        """Upsert a social connector for an account+platform pair."""
        if platform not in self.VALID_PLATFORMS:
            return {"error": f"Invalid platform: {platform}"}
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO social_connectors
                   (account_id, platform, access_token, page_id, ig_user_id, status,
                    updated_at)
                   VALUES (?,?,?,?,?,?,datetime('now'))
                   ON CONFLICT(account_id, platform) DO UPDATE SET
                     access_token=excluded.access_token,
                     page_id=excluded.page_id,
                     ig_user_id=excluded.ig_user_id,
                     status=excluded.status,
                     updated_at=datetime('now')""",
                (int(account_id), platform, access_token, page_id,
                 ig_user_id, status),
            )
            conn.commit()
            return self.get_connector(account_id, platform)
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def get_connector(self, account_id, platform):
        """Return connector record or None if not configured."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM social_connectors WHERE account_id=? AND platform=?",
                (int(account_id), platform),
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            conn.close()

    def list_connectors(self, account_id):
        """Return all connectors for an account."""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM social_connectors WHERE account_id=? ORDER BY platform",
                (int(account_id),),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def update_status(self, account_id, platform, status, last_validated_at=None):
        """Update connector status (after validation attempt)."""
        conn = get_connection()
        try:
            if last_validated_at:
                conn.execute(
                    """UPDATE social_connectors
                       SET status=?, last_validated_at=?, updated_at=datetime('now')
                       WHERE account_id=? AND platform=?""",
                    (status, last_validated_at, int(account_id), platform),
                )
            else:
                conn.execute(
                    """UPDATE social_connectors
                       SET status=?, updated_at=datetime('now')
                       WHERE account_id=? AND platform=?""",
                    (status, int(account_id), platform),
                )
            conn.commit()
            return {"success": True, "status": status}
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_connector(self, account_id, platform):
        """Call Graph API /me to validate access token; update connector status.

        Returns {"valid": bool, "user_id": str, "name": str} or error dict.
        """
        connector = self.get_connector(account_id, platform)
        if not connector or not connector.get("access_token"):
            return {"valid": False, "error": "No credentials configured"}

        from app.services.publishing_connector_service import PublishingConnectorService
        connector_svc = PublishingConnectorService()
        try:
            resp = connector_svc._http_get(
                "https://graph.facebook.com/me",
                {"access_token": connector["access_token"], "fields": "id,name"},
            )
        except Exception as e:
            self.update_status(account_id, platform, "invalid")
            return {"valid": False, "error": str(e)}

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        if "id" in resp and "error" not in resp:
            self.update_status(account_id, platform, "connected",
                               last_validated_at=now)
            self._track_usage(account_id, "connector_validation")
            return {"valid": True, "user_id": resp.get("id", ""),
                    "name": resp.get("name", ""), "platform": platform}
        else:
            err = resp.get("error", {})
            msg = err.get("message", "Validation failed") if isinstance(err, dict) else str(err)
            self.update_status(account_id, platform, "invalid")
            return {"valid": False, "error": msg}

    @staticmethod
    def _track_usage(account_id, metric):
        try:
            from app.services.billing_service import BillingService
            BillingService().track_usage(metric)
        except Exception:
            pass
