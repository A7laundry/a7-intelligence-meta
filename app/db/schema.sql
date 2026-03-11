-- A7 Intelligence Database Schema
-- SQLite3

-- Ad Accounts registry (multi-account support)
CREATE TABLE IF NOT EXISTS ad_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL DEFAULT 'meta' CHECK(platform IN ('meta', 'google')),
    account_name TEXT NOT NULL,
    external_account_id TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'paused')),
    is_default INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(platform, external_account_id)
);

CREATE INDEX IF NOT EXISTS idx_ad_accounts_platform ON ad_accounts(platform);

-- Daily account-level metrics snapshots
CREATE TABLE IF NOT EXISTS daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER DEFAULT 1,
    date TEXT NOT NULL,
    platform TEXT NOT NULL CHECK(platform IN ('meta', 'google')),
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
);

-- Campaign-level daily snapshots
CREATE TABLE IF NOT EXISTS campaign_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER DEFAULT 1,
    date TEXT NOT NULL,
    platform TEXT NOT NULL CHECK(platform IN ('meta', 'google')),
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
);

-- Optimization actions log
CREATE TABLE IF NOT EXISTS optimization_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    mode TEXT NOT NULL CHECK(mode IN ('dry_run', 'live')),
    ad_set_id TEXT,
    ad_set_name TEXT,
    rule TEXT NOT NULL,
    reason TEXT,
    action TEXT NOT NULL,
    executed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Alerts history
CREATE TABLE IF NOT EXISTS alerts_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    alert_type TEXT NOT NULL,
    severity TEXT DEFAULT 'WARNING',
    ad_set_id TEXT,
    ad_set_name TEXT,
    message TEXT NOT NULL,
    channel TEXT DEFAULT 'console',
    delivered INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_daily_snapshots_date ON daily_snapshots(date);
CREATE INDEX IF NOT EXISTS idx_daily_snapshots_account ON daily_snapshots(account_id);
CREATE INDEX IF NOT EXISTS idx_campaign_snapshots_date ON campaign_snapshots(date);
CREATE INDEX IF NOT EXISTS idx_campaign_snapshots_campaign ON campaign_snapshots(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_snapshots_account ON campaign_snapshots(account_id);
CREATE INDEX IF NOT EXISTS idx_optimization_log_timestamp ON optimization_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_log_timestamp ON alerts_log(timestamp);

-- Creative-level tracking
CREATE TABLE IF NOT EXISTS creatives (
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
);

CREATE TABLE IF NOT EXISTS creative_daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_date TEXT NOT NULL,
    creative_id INTEGER NOT NULL REFERENCES creatives(id),
    platform TEXT NOT NULL DEFAULT 'meta',
    spend REAL DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    cpa REAL DEFAULT 0,
    reach INTEGER DEFAULT 0,
    frequency REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(metric_date, creative_id)
);

CREATE INDEX IF NOT EXISTS idx_creatives_ad_id ON creatives(ad_id);
CREATE INDEX IF NOT EXISTS idx_creatives_campaign ON creatives(campaign_id);
CREATE INDEX IF NOT EXISTS idx_creatives_account ON creatives(account_id);
CREATE INDEX IF NOT EXISTS idx_creative_metrics_date ON creative_daily_metrics(metric_date);
CREATE INDEX IF NOT EXISTS idx_creative_metrics_creative ON creative_daily_metrics(creative_id);

-- AI Coach insights history
CREATE TABLE IF NOT EXISTS ai_coach_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER DEFAULT 1,
    insight_type TEXT NOT NULL,
    severity TEXT DEFAULT 'info' CHECK(severity IN ('info', 'warning', 'critical', 'success')),
    entity_type TEXT DEFAULT '',
    entity_name TEXT DEFAULT '',
    title TEXT NOT NULL,
    message TEXT DEFAULT '',
    recommendation TEXT DEFAULT '',
    payload_json TEXT DEFAULT '{}',
    period_days INTEGER DEFAULT 7,
    platform TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ai_coach_insights_type ON ai_coach_insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_ai_coach_insights_created ON ai_coach_insights(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_coach_insights_account ON ai_coach_insights(account_id);

-- Operational alerts (Budget Intelligence + Alert System)
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER DEFAULT 1,
    alert_type TEXT NOT NULL,
    severity TEXT DEFAULT 'info' CHECK(severity IN ('info', 'warning', 'critical', 'success')),
    entity_type TEXT DEFAULT '',
    entity_name TEXT DEFAULT '',
    title TEXT NOT NULL,
    message TEXT DEFAULT '',
    payload_json TEXT DEFAULT '{}',
    platform TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(resolved);
CREATE INDEX IF NOT EXISTS idx_alerts_account ON alerts(account_id);

-- Scheduled operations log
CREATE TABLE IF NOT EXISTS operations_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,
    status TEXT DEFAULT 'success' CHECK(status IN ('success', 'warning', 'failed')),
    message TEXT DEFAULT '',
    payload_json TEXT DEFAULT '{}',
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_operations_log_type ON operations_log(operation_type);
CREATE INDEX IF NOT EXISTS idx_operations_log_created ON operations_log(created_at);

-- Automation action queue
CREATE TABLE IF NOT EXISTS automation_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER DEFAULT 1,
    action_type TEXT NOT NULL CHECK(action_type IN (
        'pause_campaign', 'increase_budget', 'decrease_budget',
        'refresh_creative', 'rotate_creative'
    )),
    platform TEXT NOT NULL DEFAULT 'meta' CHECK(platform IN ('meta', 'google')),
    entity_type TEXT NOT NULL DEFAULT 'campaign',
    entity_id TEXT DEFAULT '',
    entity_name TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    confidence TEXT DEFAULT 'medium' CHECK(confidence IN ('low', 'medium', 'high')),
    suggested_change_pct REAL DEFAULT 0,
    status TEXT DEFAULT 'proposed' CHECK(status IN (
        'proposed', 'approved', 'rejected', 'executed', 'failed'
    )),
    execution_mode TEXT DEFAULT 'dry_run' CHECK(execution_mode IN ('dry_run', 'live', 'blocked')),
    created_at TEXT DEFAULT (datetime('now')),
    approved_at TEXT,
    executed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_automation_actions_status ON automation_actions(status);
CREATE INDEX IF NOT EXISTS idx_automation_actions_platform ON automation_actions(platform);
CREATE INDEX IF NOT EXISTS idx_automation_actions_created ON automation_actions(created_at);
CREATE INDEX IF NOT EXISTS idx_automation_actions_account ON automation_actions(account_id);

-- Automation execution logs (audit trail)
CREATE TABLE IF NOT EXISTS automation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER DEFAULT 1,
    action_id INTEGER REFERENCES automation_actions(id),
    platform TEXT DEFAULT '',
    entity_name TEXT DEFAULT '',
    action_type TEXT DEFAULT '',
    status TEXT DEFAULT '' CHECK(status IN ('proposed', 'approved', 'simulated', 'executed', 'failed', 'blocked', '')),
    message TEXT DEFAULT '',
    execution_time_ms INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_automation_logs_action ON automation_logs(action_id);
CREATE INDEX IF NOT EXISTS idx_automation_logs_created ON automation_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_automation_logs_account ON automation_logs(account_id);
