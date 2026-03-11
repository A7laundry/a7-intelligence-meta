"""Account Service — Manages ad accounts registry for multi-account support."""

from app.db.init_db import get_connection


class AccountService:
    """CRUD and lookup for ad_accounts table."""

    @staticmethod
    def get_all(platform: str = None) -> list:
        """Return all accounts, optionally filtered by platform."""
        conn = get_connection()
        try:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM ad_accounts WHERE platform = ? ORDER BY is_default DESC, id",
                    (platform,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ad_accounts ORDER BY is_default DESC, id"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def get_by_id(account_id: int) -> dict:
        """Return a single account by internal id."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM ad_accounts WHERE id = ?", (account_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def get_default() -> dict:
        """Return the default account (is_default=1), or the first one."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM ad_accounts ORDER BY is_default DESC, id LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def resolve_account_id(account_id_param) -> int:
        """
        Given an account_id query param (str/int/None), return a valid int id.
        Falls back to the default account if not provided or invalid.
        """
        if account_id_param is not None:
            try:
                aid = int(account_id_param)
                acc = AccountService.get_by_id(aid)
                if acc:
                    return aid
            except (ValueError, TypeError):
                pass
        default = AccountService.get_default()
        return default["id"] if default else 1

    @staticmethod
    def get_external_account_id(account_id: int) -> str:
        """Return the external_account_id (e.g. act_xxxx) for a given account."""
        acc = AccountService.get_by_id(account_id)
        return acc["external_account_id"] if acc else None
