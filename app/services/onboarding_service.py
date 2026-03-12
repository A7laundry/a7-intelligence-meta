"""Account Onboarding Service — Validate credentials, create accounts, trigger initial sync.

Supported platforms:
  meta   — requires external_account_id (act_xxx) + access_token
  google — requires customer_id + developer_token + refresh_token

The service NEVER executes live ad actions; it only validates credentials and
seeds the database with the initial data snapshot.

Meta validation:
  Calls Graph API v19.0 to verify the token has read access to the account.

Google validation:
  Exchanges refresh_token for an access_token via OAuth2 if GOOGLE_CLIENT_ID
  and GOOGLE_CLIENT_SECRET are configured; otherwise performs field-presence check.

Initial sync pipeline (trigger_initial_sync):
  1. Snapshot job  — pulls today's metrics
  2. AI refresh    — campaigns, creatives, budget intelligence
  3. Alerts refresh — evaluates alert rules
  4. Stamps last_sync on the account record
"""

import json
import os

from app.services.account_service import AccountService


class OnboardingService:
    """Validates platform credentials, creates account records, and seeds initial data."""

    # ══════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════

    def connect_meta(self, external_account_id: str, access_token: str,
                     account_name: str = None) -> dict:
        """Connect a Meta Ads account.

        Args:
            external_account_id: Meta account ID, with or without 'act_' prefix.
            access_token:        User or system access token with ads_read scope.
            account_name:        Display name override (API name used if omitted).

        Returns:
            {"success": True,  "account": {...}}  or
            {"success": False, "error": str}
        """
        ext_id = external_account_id.strip()
        if not ext_id.startswith("act_"):
            ext_id = f"act_{ext_id}"

        validation = self._validate_meta(ext_id, access_token.strip())
        if not validation["valid"]:
            return {"success": False, "error": validation["error"]}

        name = account_name or validation.get("account_name") or f"Meta {ext_id}"
        acc = AccountService.create_account(
            "meta", name, ext_id, access_token=access_token.strip()
        )
        if acc is None:
            # Account already exists — return existing record
            conn_row = self._get_by_external("meta", ext_id)
            if conn_row:
                return {"success": True, "account": conn_row, "already_connected": True}
            return {"success": False, "error": f"Account {ext_id} could not be created"}

        sync_results = self._safe_trigger_sync(acc["id"])
        return {"success": True, "account": acc, "sync": sync_results}

    def connect_google(self, customer_id: str, developer_token: str,
                       refresh_token: str, account_name: str = None) -> dict:
        """Connect a Google Ads account.

        Args:
            customer_id:     Google Ads customer ID (digits, with or without hyphens).
            developer_token: API developer token from Google Cloud Console.
            refresh_token:   OAuth2 refresh token for the Ads account.
            account_name:    Display name override.

        Returns:
            {"success": True,  "account": {...}}  or
            {"success": False, "error": str}
        """
        cid = customer_id.strip().replace("-", "")
        validation = self._validate_google(cid, developer_token.strip(), refresh_token.strip())
        if not validation["valid"]:
            return {"success": False, "error": validation["error"]}

        name = account_name or validation.get("account_name") or f"Google Ads {cid}"
        acc = AccountService.create_account(
            "google", name, cid,
            developer_token=developer_token.strip(),
            refresh_token=refresh_token.strip(),
            customer_id=cid,
        )
        if acc is None:
            conn_row = self._get_by_external("google", cid)
            if conn_row:
                return {"success": True, "account": conn_row, "already_connected": True}
            return {"success": False, "error": f"Account {cid} could not be created"}

        sync_results = self._safe_trigger_sync(acc["id"])
        return {"success": True, "account": acc, "sync": sync_results}

    def trigger_initial_sync(self, account_id: int) -> dict:
        """Run the initial data pipeline for a newly connected account.

        Steps:
          1. Snapshot   — today's account-level metrics
          2. AI refresh — campaigns, creatives, budget intelligence
          3. Alerts     — evaluate alert rules for the account

        Always stamps last_sync on the account record, even on partial failure.

        Returns a dict with per-step results.
        """
        from app.services.scheduler_service import SchedulerService
        sched = SchedulerService()
        results = {}

        try:
            results["snapshot"] = sched.run_snapshot_job()
        except Exception as e:
            results["snapshot"] = {"status": "failed", "error": str(e)}

        try:
            results["ai_refresh"] = sched.run_ai_refresh_job()
        except Exception as e:
            results["ai_refresh"] = {"status": "failed", "error": str(e)}

        try:
            results["alerts"] = sched.run_alert_refresh_job()
        except Exception as e:
            results["alerts"] = {"status": "failed", "error": str(e)}

        AccountService.update_last_sync(account_id)
        return results

    # ══════════════════════════════════════════════════════════
    # CREDENTIAL VALIDATION
    # ══════════════════════════════════════════════════════════

    def _validate_meta(self, ext_id: str, access_token: str) -> dict:
        """Verify Meta credentials by calling Graph API v19.0.

        Returns {"valid": True, "account_name": str} or {"valid": False, "error": str}.
        """
        if not access_token:
            return {"valid": False, "error": "access_token is required"}

        try:
            import urllib.request
            import urllib.error

            url = (
                f"https://graph.facebook.com/v19.0/{ext_id}"
                f"?fields=name,account_status&access_token={access_token}"
            )
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())

            if "error" in body:
                return {"valid": False,
                        "error": body["error"].get("message", "Meta API error")}
            return {"valid": True, "account_name": body.get("name", ext_id)}

        except urllib.error.HTTPError as exc:
            try:
                err_body = json.loads(exc.read())
                msg = err_body.get("error", {}).get("message", str(exc))
            except Exception:
                msg = f"Meta API HTTP {exc.code}"
            return {"valid": False, "error": msg}
        except Exception as exc:
            return {"valid": False, "error": f"Meta validation error: {str(exc)}"}

    def _validate_google(self, customer_id: str, developer_token: str,
                          refresh_token: str) -> dict:
        """Verify Google credentials.

        If GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set, exchanges the
        refresh_token for an access_token via OAuth2.  Otherwise performs a
        field-presence check and returns with a warning.

        Returns {"valid": True, "account_name": str} or {"valid": False, "error": str}.
        """
        if not customer_id:
            return {"valid": False, "error": "customer_id is required"}
        if not developer_token:
            return {"valid": False, "error": "developer_token is required"}
        if not refresh_token:
            return {"valid": False, "error": "refresh_token is required"}

        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

        if client_id and client_secret:
            return self._validate_google_oauth(customer_id, developer_token,
                                               refresh_token, client_id, client_secret)

        # Lightweight validation when OAuth client creds are not configured
        return {
            "valid": True,
            "account_name": f"Google Ads {customer_id}",
            "warning": (
                "Full OAuth validation skipped — "
                "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not configured"
            ),
        }

    def _validate_google_oauth(self, customer_id: str, developer_token: str,
                                refresh_token: str, client_id: str,
                                client_secret: str) -> dict:
        """Exchange refresh_token for access_token to verify Google credentials."""
        try:
            import urllib.request
            import urllib.parse
            import urllib.error

            payload = urllib.parse.urlencode({
                "grant_type":    "refresh_token",
                "client_id":     client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            }).encode()
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())

            if "access_token" not in body:
                return {"valid": False, "error": "Google OAuth token exchange failed"}
            return {"valid": True, "account_name": f"Google Ads {customer_id}"}

        except urllib.error.HTTPError as exc:
            try:
                err_body = json.loads(exc.read())
                msg = err_body.get("error_description", str(exc))
            except Exception:
                msg = f"Google OAuth HTTP {exc.code}"
            return {"valid": False, "error": msg}
        except Exception as exc:
            return {"valid": False, "error": f"Google validation error: {str(exc)}"}

    # ══════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════

    def _safe_trigger_sync(self, account_id: int) -> dict:
        """Run trigger_initial_sync, swallowing any exception."""
        try:
            return self.trigger_initial_sync(account_id)
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _get_by_external(platform: str, external_account_id: str) -> dict:
        """Fetch an account by platform + external_account_id."""
        from app.db.init_db import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM ad_accounts WHERE platform = ? AND external_account_id = ?",
                (platform, external_account_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
