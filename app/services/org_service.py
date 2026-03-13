"""Organization service — multi-tenant org management."""
import logging
from app.db.init_db import get_connection

logger = logging.getLogger(__name__)

DEFAULT_ORG_ID = 1


class OrgService:
    """Manages organizations and user-org membership."""

    @staticmethod
    def get_org(org_id: int = DEFAULT_ORG_ID) -> dict:
        """Get organization by ID."""
        try:
            conn = get_connection()
            row = conn.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
            conn.close()
            return dict(row) if row else {}
        except Exception:
            return {}

    @staticmethod
    def create_org(name: str, created_by: str = None) -> int:
        """Create a new organization. Returns new org_id."""
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO organizations (name, slug, created_by) VALUES (?, ?, ?)",
                (name, slug, created_by)
            )
            conn.commit()
            # Get last inserted id
            row = conn.execute("SELECT last_insert_rowid() as id").fetchone()
            org_id = row["id"] if row else None
            return org_id
        finally:
            conn.close()

    @staticmethod
    def add_user(org_id: int, supabase_user_id: str, email: str, role: str = "member") -> bool:
        """Add a user to an organization."""
        try:
            conn = get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO org_users (org_id, supabase_user_id, email, role) VALUES (?, ?, ?, ?)",
                (org_id, supabase_user_id, email, role)
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    @staticmethod
    def get_user_org(supabase_user_id: str) -> int:
        """Get the org_id for a given Supabase user. Returns DEFAULT_ORG_ID if not found."""
        try:
            conn = get_connection()
            row = conn.execute(
                "SELECT org_id FROM org_users WHERE supabase_user_id = ? LIMIT 1",
                (supabase_user_id,)
            ).fetchone()
            conn.close()
            return row["org_id"] if row else DEFAULT_ORG_ID
        except Exception:
            return DEFAULT_ORG_ID

    @staticmethod
    def list_members(org_id: int) -> list:
        """List all users in an organization."""
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT * FROM org_users WHERE org_id = ? ORDER BY created_at",
                (org_id,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []
