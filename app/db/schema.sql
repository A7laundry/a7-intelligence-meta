-- A7 Intelligence Database Schema
-- SQLite3

-- Daily account-level metrics snapshots
CREATE TABLE IF NOT EXISTS daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    UNIQUE(date, platform)
);

-- Campaign-level daily snapshots
CREATE TABLE IF NOT EXISTS campaign_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    UNIQUE(date, platform, campaign_id)
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
CREATE INDEX IF NOT EXISTS idx_campaign_snapshots_date ON campaign_snapshots(date);
CREATE INDEX IF NOT EXISTS idx_campaign_snapshots_campaign ON campaign_snapshots(campaign_id);
CREATE INDEX IF NOT EXISTS idx_optimization_log_timestamp ON optimization_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_log_timestamp ON alerts_log(timestamp);

-- Creative-level tracking
CREATE TABLE IF NOT EXISTS creatives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    UNIQUE(platform, ad_id)
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
CREATE INDEX IF NOT EXISTS idx_creative_metrics_date ON creative_daily_metrics(metric_date);
CREATE INDEX IF NOT EXISTS idx_creative_metrics_creative ON creative_daily_metrics(creative_id);

-- AI Coach insights history
CREATE TABLE IF NOT EXISTS ai_coach_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- Operational alerts (Budget Intelligence + Alert System)
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
