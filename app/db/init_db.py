"""Database initialization, migration, and connection management."""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "a7_intelligence.db")
# A7_DB_PATH allows overriding the database location via environment variable.
# On Railway, set A7_DB_PATH to a path on a persistent volume (e.g. /data/a7_intelligence.db).
DB_PATH = os.environ.get("A7_DB_PATH", _DEFAULT_DB_PATH)
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def get_db_path():
    return DB_PATH


def get_connection():
    """Get a database connection.

    Uses PostgreSQL (via DATABASE_URL) when available, falls back to SQLite for
    local development.
    """
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        from app.db.postgres_adapter import PostgresConnection
        return PostgresConnection(database_url)
    # SQLite fallback (local dev)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn, name):
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        try:
            row = conn.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = %s AND table_schema = 'public'",
                (name,)
            ).fetchone()
            return row is not None
        except Exception:
            return False
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _column_exists(conn, table, column):
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        try:
            row = conn.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s AND table_schema = 'public'",
                (table, column)
            ).fetchone()
            return row is not None
        except Exception:
            return False
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

    # Migration 8: Content Studio — ideas, brand kits, prompts, assets
    if not _table_exists(conn, "content_ideas"):
        conn.execute("""
            CREATE TABLE content_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER DEFAULT 1,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                content_type TEXT DEFAULT 'post',
                platform_target TEXT DEFAULT 'instagram',
                status TEXT DEFAULT 'idea',
                source TEXT DEFAULT 'manual',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_ideas_account ON content_ideas(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_ideas_status  ON content_ideas(status)")
        conn.commit()

    if not _table_exists(conn, "brand_kits"):
        conn.execute("""
            CREATE TABLE brand_kits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                brand_name TEXT DEFAULT '',
                primary_color TEXT DEFAULT '#000000',
                secondary_color TEXT DEFAULT '#ffffff',
                accent_color TEXT DEFAULT '#3B82F6',
                font_family TEXT DEFAULT 'Inter',
                logo_url TEXT DEFAULT '',
                style_description TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(account_id)
            )
        """)
        conn.commit()

    if not _table_exists(conn, "creative_prompts"):
        conn.execute("""
            CREATE TABLE creative_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER DEFAULT 1,
                content_idea_id INTEGER,
                prompt_text TEXT NOT NULL DEFAULT '',
                style TEXT DEFAULT 'photorealistic',
                aspect_ratio TEXT DEFAULT '1:1',
                image_type TEXT DEFAULT 'social_post',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_creative_prompts_acct ON creative_prompts(account_id)")
        conn.commit()

    if not _table_exists(conn, "creative_assets"):
        conn.execute("""
            CREATE TABLE creative_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER DEFAULT 1,
                content_idea_id INTEGER,
                asset_type TEXT DEFAULT 'image',
                asset_url TEXT DEFAULT '',
                thumbnail_url TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_creative_assets_acct   ON creative_assets(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_creative_assets_status ON creative_assets(status)")
        conn.commit()

    # Migration 9: Content Studio Phase 8B — prompt updated_at, asset generation columns
    if _table_exists(conn, "creative_prompts") and not _column_exists(conn, "creative_prompts", "updated_at"):
        conn.execute("ALTER TABLE creative_prompts ADD COLUMN updated_at TEXT")
        conn.commit()
    if _table_exists(conn, "creative_assets") and not _column_exists(conn, "creative_assets", "provider"):
        conn.execute("ALTER TABLE creative_assets ADD COLUMN provider TEXT DEFAULT 'mock'")
        conn.commit()
    if _table_exists(conn, "creative_assets") and not _column_exists(conn, "creative_assets", "generation_cost"):
        conn.execute("ALTER TABLE creative_assets ADD COLUMN generation_cost REAL DEFAULT 0.0")
        conn.commit()

    # Migration 10: Publishing Engine — content_posts and publishing_jobs
    if not _table_exists(conn, "content_posts"):
        conn.execute("""
            CREATE TABLE content_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER DEFAULT 1,
                content_idea_id INTEGER,
                creative_asset_id INTEGER,
                title TEXT NOT NULL DEFAULT '',
                caption TEXT DEFAULT '',
                platform_target TEXT DEFAULT 'instagram',
                post_type TEXT DEFAULT 'image_post' CHECK(post_type IN (
                    'image_post','carousel','story','reel','banner','ad_creative'
                )),
                status TEXT DEFAULT 'draft' CHECK(status IN (
                    'draft','scheduled','publishing','published','failed','archived'
                )),
                scheduled_for TEXT,
                published_at TEXT,
                external_post_id TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_posts_account   ON content_posts(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_posts_status    ON content_posts(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_posts_scheduled ON content_posts(scheduled_for)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_posts_platform  ON content_posts(platform_target)")
        conn.commit()

    if not _table_exists(conn, "publishing_jobs"):
        conn.execute("""
            CREATE TABLE publishing_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER DEFAULT 1,
                content_post_id INTEGER,
                platform_target TEXT DEFAULT 'instagram',
                job_type TEXT DEFAULT 'publish_now' CHECK(job_type IN ('publish_now','schedule','retry')),
                status TEXT DEFAULT 'queued' CHECK(status IN (
                    'queued','scheduled','running','success','failed','cancelled'
                )),
                scheduled_for TEXT,
                executed_at TEXT,
                result_message TEXT DEFAULT '',
                payload_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_account ON publishing_jobs(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_status  ON publishing_jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_sched   ON publishing_jobs(scheduled_for)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_post    ON publishing_jobs(content_post_id)")
        conn.commit()

    # Migration 11a: Extend publishing_jobs — new statuses + retry columns
    # On PostgreSQL, skip the sqlite_master inspection and rely solely on column check.
    if _table_exists(conn, "publishing_jobs"):
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if database_url:
            # PostgreSQL: only rebuild if the retry_count column is truly missing
            old_sql = ""
        else:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='publishing_jobs'"
            ).fetchone()
            old_sql = row[0] if row else ""
        needs_rebuild = ("'uploading'" not in old_sql or
                         not _column_exists(conn, "publishing_jobs", "retry_count"))
        if needs_rebuild:
            try:
                old_cols = ("id, account_id, content_post_id, platform_target, job_type, "
                            "status, scheduled_for, executed_at, result_message, "
                            "payload_json, created_at, updated_at")
                conn.execute("""
                    CREATE TABLE publishing_jobs_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id INTEGER DEFAULT 1,
                        content_post_id INTEGER,
                        platform_target TEXT DEFAULT 'instagram',
                        job_type TEXT DEFAULT 'publish_now',
                        status TEXT DEFAULT 'queued',
                        scheduled_for TEXT,
                        executed_at TEXT,
                        result_message TEXT DEFAULT '',
                        payload_json TEXT DEFAULT '{}',
                        retry_count INTEGER DEFAULT 0,
                        next_retry_at TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                conn.execute(
                    f"INSERT INTO publishing_jobs_new ({old_cols}, retry_count, next_retry_at) "
                    f"SELECT {old_cols}, 0, NULL FROM publishing_jobs"
                )
                conn.execute("DROP TABLE publishing_jobs")
                conn.execute("ALTER TABLE publishing_jobs_new RENAME TO publishing_jobs")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_account ON publishing_jobs(account_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_status  ON publishing_jobs(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_sched   ON publishing_jobs(scheduled_for)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_post    ON publishing_jobs(content_post_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_publishing_jobs_retry   ON publishing_jobs(next_retry_at)")
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"⚠️  Migration 11a skipped: {e}")

    # Migration 11b: social_connectors table
    if not _table_exists(conn, "social_connectors"):
        conn.execute("""
            CREATE TABLE social_connectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                access_token TEXT DEFAULT '',
                page_id TEXT DEFAULT '',
                ig_user_id TEXT DEFAULT '',
                status TEXT DEFAULT 'disconnected',
                last_validated_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(account_id, platform)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_connectors_account  ON social_connectors(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_connectors_platform ON social_connectors(platform)")
        conn.commit()

    # Migration 12a: content_metrics table
    if not _table_exists(conn, "content_metrics"):
        conn.execute("""
            CREATE TABLE content_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                content_post_id INTEGER NOT NULL,
                platform_target TEXT DEFAULT '',
                metric_date TEXT NOT NULL,
                impressions INTEGER DEFAULT 0,
                reach INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                engagement INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                saves INTEGER DEFAULT 0,
                ctr REAL DEFAULT 0.0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(content_post_id, metric_date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_metrics_account ON content_metrics(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_metrics_post    ON content_metrics(content_post_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_metrics_date    ON content_metrics(metric_date)")
        conn.commit()

    # Migration 12b: content_insights table
    if not _table_exists(conn, "content_insights"):
        conn.execute("""
            CREATE TABLE content_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                content_post_id INTEGER,
                insight_type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                message TEXT DEFAULT '',
                score REAL DEFAULT 0.0,
                payload_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_insights_account ON content_insights(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_insights_type    ON content_insights(insight_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content_insights_post    ON content_insights(content_post_id)")
        conn.commit()

    # Migration 13: composite indexes (idempotent — CREATE INDEX IF NOT EXISTS)
    composite_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_metrics_account_date ON daily_snapshots(account_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_metrics_campaign_date ON campaign_snapshots(campaign_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_status_scheduled ON publishing_jobs(status, scheduled_for)",
        "CREATE INDEX IF NOT EXISTS idx_ops_log_type_ts ON operations_log(operation_type, started_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_alerts_account_ts ON alerts(account_id, created_at DESC)",
    ]
    for idx_sql in composite_indexes:
        try:
            conn.execute(idx_sql)
        except Exception:
            pass
    conn.commit()

    # Migration 14: currency column on ad_accounts
    if _table_exists(conn, "ad_accounts") and not _column_exists(conn, "ad_accounts", "currency"):
        conn.execute("ALTER TABLE ad_accounts ADD COLUMN currency TEXT DEFAULT 'USD'")
        conn.commit()

    # Migration 15: frequency, reach, cpm columns on ad_metrics (if table exists)
    if _table_exists(conn, "ad_metrics"):
        if not _column_exists(conn, "ad_metrics", "frequency"):
            conn.execute("ALTER TABLE ad_metrics ADD COLUMN frequency REAL")
            conn.commit()
        if not _column_exists(conn, "ad_metrics", "reach"):
            conn.execute("ALTER TABLE ad_metrics ADD COLUMN reach INTEGER")
            conn.commit()
        if not _column_exists(conn, "ad_metrics", "cpm"):
            conn.execute("ALTER TABLE ad_metrics ADD COLUMN cpm REAL")
            conn.commit()

    # Migration 16: conversion_value column on daily_snapshots and campaign_snapshots
    if not _column_exists(conn, "daily_snapshots", "conversion_value"):
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN conversion_value REAL DEFAULT 0")
    if not _column_exists(conn, "campaign_snapshots", "conversion_value"):
        conn.execute("ALTER TABLE campaign_snapshots ADD COLUMN conversion_value REAL DEFAULT 0")
    conn.commit()

    # Migration 17a: add updated_at to ad_accounts (used by update_account_token)
    if _table_exists(conn, "ad_accounts") and not _column_exists(conn, "ad_accounts", "updated_at"):
        conn.execute("ALTER TABLE ad_accounts ADD COLUMN updated_at TEXT")
        conn.commit()

    # Migration 17b: add account_id to automation_logs (used by get_logs account filter)
    if _table_exists(conn, "automation_logs") and not _column_exists(conn, "automation_logs", "account_id"):
        conn.execute("ALTER TABLE automation_logs ADD COLUMN account_id INTEGER DEFAULT 1")
        conn.commit()

    # Migration 17: add organizations, org_users tables + stripe_customer_id
    if not _table_exists(conn, "organizations"):
        conn.execute("""CREATE TABLE organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE,
            status TEXT DEFAULT 'active',
            created_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""")
        # Seed default org
        conn.execute("INSERT OR IGNORE INTO organizations (id, name, slug) VALUES (1, 'Default', 'default')")

    if not _table_exists(conn, "org_users"):
        conn.execute("""CREATE TABLE org_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL REFERENCES organizations(id),
            supabase_user_id TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT DEFAULT 'member',
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(org_id, supabase_user_id)
        )""")

    if not _column_exists(conn, "subscriptions", "stripe_customer_id"):
        conn.execute("ALTER TABLE subscriptions ADD COLUMN stripe_customer_id TEXT")

    conn.commit()

    # Migration 18: pulse_insights — persistent Performance Pulse tracking
    if not _table_exists(conn, "pulse_insights"):
        conn.execute("""
            CREATE TABLE pulse_insights (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id       INTEGER NOT NULL,
                fingerprint      TEXT    NOT NULL,
                rule_type        TEXT    NOT NULL,
                signal           TEXT    NOT NULL,
                priority         INTEGER NOT NULL DEFAULT 5,
                title            TEXT    NOT NULL,
                body             TEXT    NOT NULL DEFAULT '',
                metric           TEXT,
                action_label     TEXT,
                action_page      TEXT,
                state            TEXT    NOT NULL DEFAULT 'new'
                                        CHECK(state IN ('new','persistent','reviewed','resolved','recovered')),
                first_seen_at    TEXT    NOT NULL DEFAULT (datetime('now')),
                last_seen_at     TEXT    NOT NULL DEFAULT (datetime('now')),
                resolved_at      TEXT,
                reviewed_at      TEXT,
                occurrence_count INTEGER NOT NULL DEFAULT 1,
                history_json     TEXT    NOT NULL DEFAULT '[]',
                UNIQUE(account_id, fingerprint)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pulse_account ON pulse_insights(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pulse_state   ON pulse_insights(account_id, state)")
        conn.commit()

    # Migration 19: Campaign Launch Console tables
    if not _table_exists(conn, "launch_jobs"):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS launch_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                job_name TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'draft',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                published_at TEXT,
                total_items INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                template_id INTEGER,
                notes TEXT,
                FOREIGN KEY (account_id) REFERENCES ad_accounts(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_launch_jobs_account ON launch_jobs(account_id)")
        conn.commit()

    if not _table_exists(conn, "launch_items"):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS launch_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                launch_job_id INTEGER NOT NULL,
                lp_url TEXT NOT NULL,
                campaign_name TEXT,
                adset_name TEXT,
                ad_name TEXT,
                objective TEXT DEFAULT 'OUTCOME_LEADS',
                budget REAL DEFAULT 0,
                budget_type TEXT DEFAULT 'DAILY',
                headline TEXT,
                primary_text TEXT,
                description TEXT,
                cta TEXT DEFAULT 'LEARN_MORE',
                creative_key TEXT,
                creative_id INTEGER,
                geo TEXT DEFAULT 'BR',
                age_min INTEGER DEFAULT 18,
                age_max INTEGER DEFAULT 65,
                placements TEXT DEFAULT 'automatic',
                optimization_goal TEXT DEFAULT 'LEAD_GENERATION',
                pixel_id TEXT,
                page_id TEXT,
                instagram_actor_id TEXT,
                utm_source TEXT,
                utm_campaign TEXT,
                validation_status TEXT DEFAULT 'pending',
                validation_errors TEXT,
                publish_status TEXT DEFAULT 'pending',
                meta_campaign_id TEXT,
                meta_adset_id TEXT,
                meta_ad_id TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                published_at TEXT,
                row_index INTEGER DEFAULT 0,
                FOREIGN KEY (launch_job_id) REFERENCES launch_jobs(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_launch_items_job ON launch_items(launch_job_id)")
        conn.commit()

    if not _table_exists(conn, "launch_logs"):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS launch_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                launch_job_id INTEGER NOT NULL,
                launch_item_id INTEGER,
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                request_payload TEXT,
                response_payload TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (launch_job_id) REFERENCES launch_jobs(id),
                FOREIGN KEY (launch_item_id) REFERENCES launch_items(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_launch_logs_job ON launch_logs(launch_job_id)")
        conn.commit()

    if not _table_exists(conn, "launch_templates"):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS launch_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                template_name TEXT NOT NULL,
                objective TEXT DEFAULT 'OUTCOME_LEADS',
                budget_type TEXT DEFAULT 'DAILY',
                default_budget REAL DEFAULT 50.0,
                geo TEXT DEFAULT 'BR',
                age_min INTEGER DEFAULT 18,
                age_max INTEGER DEFAULT 65,
                placements TEXT DEFAULT 'automatic',
                optimization_goal TEXT DEFAULT 'LEAD_GENERATION',
                billing_event TEXT DEFAULT 'IMPRESSIONS',
                cta TEXT DEFAULT 'LEARN_MORE',
                campaign_name_pattern TEXT DEFAULT 'A7-{ACCOUNT}-{OBJECTIVE}-{DATE}-{INDEX}',
                adset_name_pattern TEXT DEFAULT '{GEO}-18-65-{PLACEMENT}',
                ad_name_pattern TEXT DEFAULT '{LPKEY}-{CTA}',
                special_ad_category TEXT DEFAULT 'NONE',
                attribution_setting TEXT DEFAULT '7d_click',
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES ad_accounts(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_launch_templates_account ON launch_templates(account_id)")
        conn.commit()

    # Migration 19b: add new columns to ad_accounts for Launch Console
    for col_def in [
        ("bm_id",                "TEXT"),
        ("page_id",              "TEXT"),
        ("instagram_actor_id",   "TEXT"),
        ("pixel_id",             "TEXT"),
        ("timezone",             "TEXT DEFAULT 'America/Sao_Paulo'"),
    ]:
        col, col_type = col_def
        if _table_exists(conn, "ad_accounts") and not _column_exists(conn, "ad_accounts", col):
            try:
                conn.execute(f"ALTER TABLE ad_accounts ADD COLUMN {col} {col_type}")
                conn.commit()
            except Exception:
                pass

    # Migration 20: Creative Library — Meta image_hash persistence for Launch Console
    if not _table_exists(conn, "creative_library"):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS creative_library (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id       INTEGER NOT NULL,
                creative_key     TEXT NOT NULL,
                original_filename TEXT,
                file_type        TEXT,
                source_type      TEXT NOT NULL DEFAULT 'upload',
                meta_image_hash  TEXT,
                meta_creative_id TEXT,
                storage_url      TEXT,
                width            INTEGER,
                height           INTEGER,
                aspect_ratio     TEXT,
                status           TEXT NOT NULL DEFAULT 'pending',
                error_message    TEXT,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES ad_accounts(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_creative_lib_account ON creative_library(account_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_creative_lib_key ON creative_library(account_id, creative_key)")
        conn.commit()

    if not _table_exists(conn, "creative_upload_logs"):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS creative_upload_logs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                creative_library_id INTEGER NOT NULL,
                account_id          INTEGER NOT NULL,
                step                TEXT NOT NULL,
                status              TEXT NOT NULL,
                message             TEXT,
                request_payload     TEXT,
                response_payload    TEXT,
                error_message       TEXT,
                created_at          TEXT NOT NULL,
                FOREIGN KEY (creative_library_id) REFERENCES creative_library(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_creative_upload_logs ON creative_upload_logs(creative_library_id)")
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
    """Recreate a table with updated UNIQUE constraint, preserving data.

    On PostgreSQL this migration is skipped — tables are created fresh from
    schema.sql with the correct constraints, so no rebuild is needed.
    """
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return  # PostgreSQL: schema.sql already has correct constraints

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
