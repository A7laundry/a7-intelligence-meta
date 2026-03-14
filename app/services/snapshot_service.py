"""Snapshot Service — Stores and retrieves daily metrics snapshots."""

import logging
from datetime import datetime, timedelta

from app.db.init_db import get_connection

_logger = logging.getLogger("a7.snapshots")


class SnapshotService:
    """Persists daily metrics to SQLite for historical analysis."""

    @staticmethod
    def save_daily_snapshot(date: str, platform: str, metrics: dict, account_id: int = 1):
        """Save or update an account-level daily snapshot."""
        conn = get_connection()
        try:
            spend = metrics.get("spend", 0)
            conversion_value = metrics.get("conversion_value", 0)
            roas = round(conversion_value / spend, 4) if spend > 0 else 0
            conn.execute(
                """INSERT INTO daily_snapshots
                   (account_id, date, platform, spend, impressions, clicks, ctr, cpc, conversions, conversion_value, cpa, roas)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(account_id, date, platform) DO UPDATE SET
                     spend=excluded.spend, impressions=excluded.impressions,
                     clicks=excluded.clicks, ctr=excluded.ctr, cpc=excluded.cpc,
                     conversions=excluded.conversions, conversion_value=excluded.conversion_value,
                     cpa=excluded.cpa, roas=excluded.roas""",
                (account_id, date, platform,
                 spend, metrics.get("impressions", 0),
                 metrics.get("clicks", 0), metrics.get("ctr", 0),
                 metrics.get("cpc", 0), metrics.get("conversions", 0),
                 conversion_value, metrics.get("cpa", 0), roas),
            )
            conn.commit()
            _logger.info(
                "[snapshot] date=%s platform=%s account=%s spend=%.2f",
                date,
                platform,
                account_id,
                spend,
            )
        finally:
            conn.close()

    @staticmethod
    def save_campaign_snapshot(date: str, platform: str, campaign: dict, account_id: int = 1):
        """Save or update a campaign-level daily snapshot."""
        conn = get_connection()
        try:
            spend = campaign.get("spend", 0)
            conversion_value = campaign.get("conversion_value", 0)
            roas = round(conversion_value / spend, 4) if spend > 0 else 0
            conn.execute(
                """INSERT INTO campaign_snapshots
                   (account_id, date, platform, campaign_id, campaign_name, status, spend, impressions, clicks, ctr, conversions, conversion_value, cpa, roas)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(account_id, date, platform, campaign_id) DO UPDATE SET
                     campaign_name=excluded.campaign_name, status=excluded.status,
                     spend=excluded.spend, impressions=excluded.impressions,
                     clicks=excluded.clicks, ctr=excluded.ctr,
                     conversions=excluded.conversions, conversion_value=excluded.conversion_value,
                     cpa=excluded.cpa, roas=excluded.roas""",
                (account_id, date, platform, campaign.get("id", ""), campaign.get("name", ""),
                 campaign.get("status", "UNKNOWN"), spend,
                 campaign.get("impressions", 0), campaign.get("clicks", 0),
                 campaign.get("ctr", 0), campaign.get("conversions", 0),
                 conversion_value, campaign.get("cpa", 0), roas),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_daily_snapshots(platform: str = None, days: int = 30, account_id: int = None) -> list:
        """Get daily snapshots for the last N days, optionally filtered by account."""
        conn = get_connection()
        try:
            since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            filters = ["date >= ?"]
            params = [since]
            if platform:
                filters.append("platform = ?")
                params.append(platform)
            if account_id is not None:
                filters.append("account_id = ?")
                params.append(account_id)
            where = " AND ".join(filters)
            rows = conn.execute(
                f"SELECT * FROM daily_snapshots WHERE {where} ORDER BY date",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def get_campaign_history(campaign_id: str, days: int = 30, account_id: int = None) -> list:
        """Get historical snapshots for a specific campaign."""
        conn = get_connection()
        try:
            since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            if account_id is not None:
                rows = conn.execute(
                    "SELECT * FROM campaign_snapshots WHERE campaign_id = ? AND account_id = ? AND date >= ? ORDER BY date",
                    (campaign_id, account_id, since),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM campaign_snapshots WHERE campaign_id = ? AND date >= ? ORDER BY date",
                    (campaign_id, since),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def get_all_campaigns_latest(account_id: int = None) -> list:
        """Get the most recent snapshot for each campaign, optionally filtered by account."""
        conn = get_connection()
        try:
            if account_id is not None:
                rows = conn.execute(
                    """SELECT cs.* FROM campaign_snapshots cs
                       INNER JOIN (
                         SELECT campaign_id, MAX(date) as max_date
                         FROM campaign_snapshots WHERE account_id = ? GROUP BY campaign_id
                       ) latest ON cs.campaign_id = latest.campaign_id AND cs.date = latest.max_date
                       WHERE cs.account_id = ?
                       ORDER BY cs.spend DESC""",
                    (account_id, account_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT cs.* FROM campaign_snapshots cs
                       INNER JOIN (
                         SELECT campaign_id, MAX(date) as max_date
                         FROM campaign_snapshots GROUP BY campaign_id
                       ) latest ON cs.campaign_id = latest.campaign_id AND cs.date = latest.max_date
                       ORDER BY cs.spend DESC""",
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def get_period_comparison(days_current: int = 7, account_id: int = None) -> dict:
        """Compare current period vs previous period of same length."""
        conn = get_connection()
        try:
            now = datetime.utcnow()
            current_start = (now - timedelta(days=days_current)).strftime("%Y-%m-%d")
            prev_start = (now - timedelta(days=days_current * 2)).strftime("%Y-%m-%d")
            prev_end = current_start

            acc_filter = " AND account_id = ?" if account_id is not None else ""

            def sum_period(start, end=None):
                base = (
                    "SELECT SUM(spend) as spend, SUM(impressions) as impressions, "
                    "SUM(clicks) as clicks, SUM(conversions) as conversions "
                    "FROM daily_snapshots WHERE date >= ?"
                )
                params = [start]
                if end:
                    base += " AND date < ?"
                    params.append(end)
                if account_id is not None:
                    base += " AND account_id = ?"
                    params.append(account_id)
                rows = conn.execute(base, params).fetchone()
                r = dict(rows) if rows else {}
                return {k: (v or 0) for k, v in r.items()}

            current = sum_period(current_start)
            previous = sum_period(prev_start, prev_end)

            def pct_change(curr, prev):
                if prev == 0:
                    return 100.0 if curr > 0 else 0.0
                return round((curr - prev) / prev * 100, 1)

            return {
                "current": current,
                "previous": previous,
                "changes": {
                    "spend": pct_change(current["spend"], previous["spend"]),
                    "impressions": pct_change(current["impressions"], previous["impressions"]),
                    "clicks": pct_change(current["clicks"], previous["clicks"]),
                    "conversions": pct_change(current["conversions"], previous["conversions"]),
                },
            }
        finally:
            conn.close()
