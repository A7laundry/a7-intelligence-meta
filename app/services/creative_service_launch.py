"""
CreativeLaunchService — Creative Library for Campaign Launch Console.

Handles image upload to Meta, image_hash persistence, and creative
validation for launch items.

Account-safe: every operation requires account_id.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime
from typing import Optional

from app.db.init_db import get_connection

_now = lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE_MB = 30


class CreativeLaunchService:

    # ── Upload ─────────────────────────────────────────────────────────────

    @classmethod
    def upload_image(
        cls,
        account_id: int,
        file_bytes: bytes,
        original_filename: str,
        creative_key: str = None,
        source_type: str = "upload",
    ) -> dict:
        """
        Upload an image to Meta for the given account.
        Returns creative_library row dict with meta_image_hash.
        Raises on any failure — never returns fake success.
        """
        # Validate file type
        ext = os.path.splitext(original_filename.lower())[1]
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # Validate file size
        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(
                f"File too large ({size_mb:.1f} MB). Maximum: {MAX_FILE_SIZE_MB} MB"
            )

        # Generate creative_key if not provided
        if not creative_key:
            h = hashlib.md5(file_bytes).hexdigest()[:8]
            base = os.path.splitext(original_filename)[0][:20]
            creative_key = f"{base}-{h}"

        # Get account
        conn = get_connection()
        try:
            account = conn.execute(
                "SELECT * FROM ad_accounts WHERE id=?", (account_id,)
            ).fetchone()
            if not account:
                raise ValueError(f"Account {account_id} not found")
            account = dict(account)
        finally:
            conn.close()

        # Insert pending record
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT INTO creative_library
                   (account_id, creative_key, original_filename, file_type,
                    source_type, status, created_at, updated_at)
                   VALUES (?,?,?,?,'upload','pending',?,?)""",
                (account_id, creative_key, original_filename, ext.lstrip("."),
                 _now(), _now()),
            )
            lib_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

        # Upload to Meta
        try:
            from meta_client import MetaAdsClient
            client = MetaAdsClient(
                account_id=account["external_account_id"],
                access_token=account["access_token"],
            )

            # Write bytes to temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            try:
                _log_upload(lib_id, account_id, "upload_to_meta", "info",
                            f"Uploading {original_filename} ({size_mb:.2f} MB) to Meta")
                image_hash = client.upload_image(tmp_path)
            finally:
                os.unlink(tmp_path)

            if not image_hash:
                raise RuntimeError("Meta returned empty image_hash")

            # Persist success
            conn = get_connection()
            try:
                conn.execute(
                    """UPDATE creative_library
                       SET meta_image_hash=?, status='uploaded', error_message=NULL, updated_at=?
                       WHERE id=?""",
                    (image_hash, _now(), lib_id),
                )
                conn.commit()
            finally:
                conn.close()

            _log_upload(lib_id, account_id, "upload_to_meta", "success",
                        f"image_hash received: {image_hash}",
                        response_payload=image_hash)

            return cls.get_creative(lib_id)

        except Exception as e:
            # Persist failure
            conn = get_connection()
            try:
                conn.execute(
                    """UPDATE creative_library
                       SET status='failed', error_message=?, updated_at=?
                       WHERE id=?""",
                    (str(e), _now(), lib_id),
                )
                conn.commit()
            finally:
                conn.close()

            _log_upload(lib_id, account_id, "upload_to_meta", "error",
                        f"Upload failed: {e}", error_message=str(e))
            raise

    # ── Library management ─────────────────────────────────────────────────

    @staticmethod
    def list_creatives(account_id: int, status: str = None) -> list:
        conn = get_connection()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM creative_library WHERE account_id=? AND status=? ORDER BY created_at DESC",
                    (account_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM creative_library WHERE account_id=? ORDER BY created_at DESC",
                    (account_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def get_creative(creative_id: int) -> Optional[dict]:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM creative_library WHERE id=?", (creative_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def get_by_key(account_id: int, creative_key: str) -> Optional[dict]:
        """Find the most recent uploaded creative for a given key+account."""
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT * FROM creative_library
                   WHERE account_id=? AND creative_key=? AND status='uploaded'
                   ORDER BY created_at DESC LIMIT 1""",
                (account_id, creative_key),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def assign_key(creative_id: int, account_id: int, creative_key: str) -> dict:
        """Update the creative_key for an existing creative."""
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE creative_library SET creative_key=?, updated_at=? WHERE id=? AND account_id=?",
                (creative_key, _now(), creative_id, account_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM creative_library WHERE id=?", (creative_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def archive_creative(creative_id: int, account_id: int) -> bool:
        conn = get_connection()
        try:
            cur = conn.execute(
                "UPDATE creative_library SET status='archived', updated_at=? WHERE id=? AND account_id=?",
                (_now(), creative_id, account_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    @staticmethod
    def get_logs(creative_id: int) -> list:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM creative_upload_logs WHERE creative_library_id=? ORDER BY id",
                (creative_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Validation helpers ─────────────────────────────────────────────────

    @classmethod
    def validate_creative_key(cls, account_id: int, creative_key: str) -> dict:
        """
        Check whether a creative_key maps to a valid uploaded hash.
        Returns dict with: valid(bool), image_hash(str|None), error(str|None)
        """
        if not creative_key:
            return {"valid": False, "image_hash": None,
                    "error": "No creative_key specified"}

        creative = cls.get_by_key(account_id, creative_key)
        if not creative:
            return {"valid": False, "image_hash": None,
                    "error": f"creative_key '{creative_key}' not found in library for this account"}

        if creative["status"] == "failed":
            return {"valid": False, "image_hash": None,
                    "error": f"Creative '{creative_key}' upload failed: {creative.get('error_message')}"}

        if creative["status"] == "archived":
            return {"valid": False, "image_hash": None,
                    "error": f"Creative '{creative_key}' is archived"}

        if not creative.get("meta_image_hash"):
            return {"valid": False, "image_hash": None,
                    "error": f"Creative '{creative_key}' has no Meta image_hash (upload may be incomplete)"}

        return {
            "valid": True,
            "image_hash": creative["meta_image_hash"],
            "creative_id": creative["id"],
            "error": None,
        }

    @classmethod
    def resolve_image_hash(cls, account_id: int, creative_key: str) -> Optional[str]:
        """Return image_hash for a creative_key, or None if not found/invalid."""
        result = cls.validate_creative_key(account_id, creative_key)
        return result.get("image_hash") if result["valid"] else None


# ── Internal helpers ───────────────────────────────────────────────────────

def _log_upload(creative_library_id: int, account_id: int, step: str,
                status: str, message: str,
                request_payload: str = None, response_payload: str = None,
                error_message: str = None):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO creative_upload_logs
               (creative_library_id, account_id, step, status, message,
                request_payload, response_payload, error_message, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (creative_library_id, account_id, step, status, message,
             request_payload, response_payload, error_message, _now()),
        )
        conn.commit()
    except Exception:
        pass  # Never block the main flow for logging failure
    finally:
        conn.close()
