"""Database initialization, migration, and connection management."""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data", "a7_intelligence.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def get_db_path():
    return DB_PATH


def get_connection():
    """Get a SQLite connection with row_factory for dict-like access."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _column_exists(conn, table, column):
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(c["name"] == column for c in cols)


def _run_migrations(conn):
    """Apply incremental migrations to existing databases."""

    # Migration 1: Add ad_accounts table and account_id columns
    if not _table_exists(conn, "ad_accounts"):
        conn.execute("""
            CREATE TABLE ad_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL DEFAULT 'meta',
                account_name TEXT NOT NULL,
                external_account_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                is_default INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(platform, external_account_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ad_accounts_platform ON ad_accounts(platform)")
        conn.commit()

    # Migration 2: Seed default accounts if empty
    count = conn.execute("SELECT COUNT(*) FROM ad_accounts").fetchone()[0]
    if count == 0:
        _seed_default_accounts(conn)

    # Migration 3: Add account_id to tables that don't have it yet
    tables_to_migrate = [
        "daily_snapshots", "campaign_snapshots", "creatives",
        "ai_coach_insights", "alerts", "automation_actions",
        "automation_logs", "creative_daily_metrics",
    ]
    for table in tables_to_migrate:
        if _table_exists(conn, table) and not _column_exists(conn, table, "account_id"):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN account_id INTEGER DEFAULT 1")
    conn.commit()

    # Migration 4: Recreate daily_snapshots with new UNIQUE(account_id, date, platform)
    #   only if old constraint UNIQUE(date, platform) without account_id is still in place
    _migrate_snapshots_table(conn, "daily_snapshots",
        """CREATE TABLE daily_snapshots_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER DEFAULT 1,
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            spend REAL DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            ctr REAL DEFAULT 0,
            cpc REAL DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            cpa REAL DEFAULT 0,
            roas REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(account_id, date, platform)
        )""",
        "INSERT INTO daily_snapshots_new SELECT id, COALESCE(account_id,1), date, platform, spend, impressions, clicks, ctr, cpc, conversions, cpa, roas, created_at FROM daily_snapshots"
    )

    _migrate_snapshots_table(conn, "campaign_snapshots",
        """CREATE TABLE campaign_snapshots_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER DEFAULT 1,
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            campaign_id TEXT NOT NULL,
            campaign_name TEXT NOT NULL,
            status TEXT DEFAULT 'UNKNOWN',
            spend REAL DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            ctr REAL DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            cpa REAL DEFAULT 0,
            roas REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(account_id, date, platform, campaign_id)
        )""",
        "INSERT INTO campaign_snapshots_new SELECT id, COALESCE(account_id,1), date, platform, campaign_id, campaign_name, status, spend, impressions, clicks, ctr, conversions, cpa, roas, created_at FROM campaign_snapshots"
    )

    # Migration 5: Add automation_runs table
    if not _table_exists(conn, "automation_runs"):
        conn.execute("""
            CREATE TABLE automation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER DEFAULT 1,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                proposals_generated INTEGER DEFAULT 0,
                actions_executed INTEGER DEFAULT 0,
                actions_failed INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running' CHECK(status IN ('running', 'success', 'failed')),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_automation_runs_account ON automation_runs(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_automation_runs_started ON automation_runs(started_at)")
        conn.commit()

    # Migration 6: Add credential + sync columns to ad_accounts
    for col_def in [
        ("access_token",    "TEXT"),
        ("developer_token", "TEXT"),
        ("refresh_token",   "TEXT"),
        ("customer_id",     "TEXT"),
        ("last_sync",       "TEXT"),
    ]:
        col, col_type = col_def
        if _table_exists(conn, "ad_accounts") and not _column_exists(conn, "ad_accounts", col):
            conn.execute(f"ALTER TABLE ad_accounts ADD COLUMN {col} {col_type}")
    conn.commit()

    # Migration 7: Billing — plans, subscriptions, usage_metrics
    if not _table_exists(conn, "plans"):
        conn.execute("""
            CREATE TABLE plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                price REAL DEFAULT 0,
                accounts_limit INTEGER,
                automation_runs_limit INTEGER,
                copilot_queries_limit INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Seed default plans
        conn.executemany(
            "INSERT OR IGNORE INTO plans (name, price, accounts_limit, automation_runs_limit, copilot_queries_limit) VALUES (?,?,?,?,?)",
            [
                ("Starter", 0.0,   2,    100,  200),
                ("Growth",  99.0,  10,   1000, 2000),
                ("Scale",   299.0, None, None, None),
            ]
        )
        conn.commit()

    if not _table_exists(conn, "subscriptions"):
        conn.execute("""
            CREATE TABLE subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL DEFAULT 1,
                plan_id INTEGER NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(organization_id)
            )
        """)
        # Seed default subscription: org 1 → Starter plan
        conn.execute("""
            INSERT OR IGNORE INTO subscriptions (organization_id, plan_id, status)
            SELECT 1, id, 'active' FROM plans WHERE name='Starter' LIMIT 1
        """)
        conn.commit()

    if not _table_exists(conn, "usage_metrics"):
        conn.execute("""
            CREATE TABLE usage_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL DEFAULT 1,
                metric TEXT NOT NULL,
                value INTEGER DEFAULT 1,
                period TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_metrics_org    ON usage_metrics(organization_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_metrics_metric ON usage_metrics(metric, period)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_org    ON subscriptions(organization_id)")
        conn.commit()

    _migrate_snapshots_table(conn, "creatives",
        """CREATE TABLE creatives_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER DEFAULT 1,
            platform TEXT NOT NULL DEFAULT 'meta',
            campaign_id TEXT,
            campaign_name TEXT,
            adset_id TEXT,
            adset_name TEXT,
            ad_id TEXT NOT NULL,
            creative_name TEXT,
            creative_type TEXT DEFAULT 'image',
            thumbnail_url TEXT,
            body_text TEXT,
            headline TEXT,
            call_to_action TEXT,
            status TEXT DEFAULT 'ACTIVE',
            last_seen_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(account_id, platform, ad_id)
        )""",
        "INSERT INTO creatives_new SELECT id, COALESCE(account_id,1), platform, campaign_id, campaign_name, adset_id, adset_name, ad_id, creative_name, creative_type, thumbnail_url, body_text, headline, call_to_action, status, last_seen_at, created_at, updated_at FROM creatives"
    )


def _migrate_snapshots_table(conn, table_name, create_sql, copy_sql):
    """Recreate a table with updated UNIQUE constraint, preserving data."""
    new_name = table_name + "_new"
    # Skip if migration already done (new table doesn't exist as tmp)
    if _table_exists(conn, new_name):
        conn.execute(f"DROP TABLE {new_name}")
        conn.commit()
    # Check if old table uses old unique constraint by inspecting sql
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    if row is None:
        return
    old_sql = row[0] or ""
    # If new constraint already in place, skip
    if "account_id, date, platform" in old_sql or "account_id, platform, ad_id" in old_sql:
        return
    try:
        conn.execute(create_sql)
        conn.execute(copy_sql)
        conn.execute(f"DROP TABLE {table_name}")
        conn.execute(f"ALTER TABLE {new_name} RENAME TO {table_name}")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"⚠️  Migration skipped for {table_name}: {e}")


def _seed_default_accounts(conn):
    """Seed the two default A7 ad accounts."""
    accounts = [
        ("meta", "A7 Laundry Orlando", "act_650201661142284", "active", 1),
        ("meta", "A7 Lavanderia SP", "act_1376004546770063", "active", 0),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO ad_accounts (platform, account_name, external_account_id, status, is_default) VALUES (?,?,?,?,?)",
        accounts,
    )
    conn.commit()


def init_db():
    """Initialize the database and run migrations."""
    conn = get_connection()
    # Execute schema statements individually — skip ones that fail on existing tables
    # (e.g. indexes referencing account_id columns not yet added by migration)
    with open(SCHEMA_PATH, "r") as f:
        sql = f.read()
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception:
                pass  # gracefully skip — migration will add missing columns next
    conn.commit()
    # Now run migrations to add missing columns and re-try any skipped indexes
    _run_migrations(conn)
    # Re-run schema to pick up any indexes that were skipped before migration
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt and stmt.upper().startswith("CREATE INDEX"):
            try:
                conn.execute(stmt)
            except Exception:
                pass
    conn.commit()
    conn.close()
    print(f"✅ Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()
