"""Command Center API — single endpoint aggregating all Overview page data."""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from app.db.init_db import get_connection

cc_bp = Blueprint("command_center", __name__)


@cc_bp.route("/command-center")
def command_center():
    account_id = request.args.get("account_id", type=int) or 1

    conn = get_connection()
    try:
        now = datetime.utcnow()
        seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        # ── KPIs: 7-day spend / conversions / CPA from daily_snapshots ──────────
        kpi = conn.execute(
            """
            SELECT
                COALESCE(SUM(spend), 0)       AS spend_7d,
                COALESCE(SUM(conversions), 0) AS conv_7d
            FROM daily_snapshots
            WHERE date >= ? AND account_id = ?
            """,
            (seven_days_ago, account_id),
        ).fetchone()

        spend_7d = kpi["spend_7d"]
        conv_7d  = kpi["conv_7d"]
        cpa_7d   = round(spend_7d / conv_7d, 2) if conv_7d > 0 else None

        # ── KPIs: today's spend / conversions / CPA ────────────────────────────
        today_str = now.strftime("%Y-%m-%d")
        kpi_today = conn.execute(
            """
            SELECT
                COALESCE(SUM(spend), 0)       AS spend_today,
                COALESCE(SUM(conversions), 0) AS conv_today
            FROM daily_snapshots
            WHERE date = ? AND account_id = ?
            """,
            (today_str, account_id),
        ).fetchone()

        spend_today = kpi_today["spend_today"]
        conv_today  = kpi_today["conv_today"]
        cpa_today   = round(spend_today / conv_today, 2) if conv_today > 0 else None

        # ── Growth Score (computed via service, cached) ───────────────────────────
        growth_score = None
        growth_label = None
        try:
            from app.services.growth_score_service import GrowthScoreService
            gs_result = GrowthScoreService().build_growth_score(days=7, account_id=account_id)
            growth_score = gs_result.get("score")
            growth_label = gs_result.get("label")
        except Exception:
            pass

        # ── Alerts: top 3 unresolved by severity ─────────────────────────────────
        sev_order = "CASE severity WHEN 'critical' THEN 1 WHEN 'warning' THEN 2 WHEN 'info' THEN 3 ELSE 4 END"
        raw_alerts = conn.execute(
            f"""
            SELECT id, alert_type, severity, title, message, created_at
            FROM alerts
            WHERE resolved = 0 AND account_id = ?
            ORDER BY {sev_order}, created_at DESC
            LIMIT 3
            """,
            (account_id,),
        ).fetchall()

        # ── Pending automation actions ────────────────────────────────────────────
        pending_auto = conn.execute(
            "SELECT COUNT(*) AS cnt FROM automation_actions WHERE status = 'proposed' AND account_id = ?",
            (account_id,),
        ).fetchone()["cnt"]

        # ── Stale connectors (last_sync > 24 h ago or NULL) ───────────────────────
        stale_thresh = (now - timedelta(hours=24)).isoformat()
        stale_count = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM ad_accounts
            WHERE status = 'active'
              AND (last_sync IS NULL OR last_sync < ?)
            """,
            (stale_thresh,),
        ).fetchone()["cnt"]

        # ── Opportunities: high-CPA campaigns ────────────────────────────────────
        high_cpa = conn.execute(
            """
            SELECT campaign_name, AVG(cpa) AS avg_cpa
            FROM campaign_snapshots
            WHERE date >= ? AND cpa > 0 AND account_id = ?
            GROUP BY campaign_id
            ORDER BY avg_cpa DESC
            LIMIT 2
            """,
            (seven_days_ago, account_id),
        ).fetchall()

        best_ctr = conn.execute(
            """
            SELECT campaign_name, AVG(ctr) AS avg_ctr
            FROM campaign_snapshots
            WHERE date >= ? AND ctr > 0 AND account_id = ?
            GROUP BY campaign_id
            ORDER BY avg_ctr DESC
            LIMIT 1
            """,
            (seven_days_ago, account_id),
        ).fetchall()

        content_pending = conn.execute(
            "SELECT COUNT(*) AS cnt FROM content_ideas WHERE status IN ('idea', 'draft') AND account_id = ?",
            (account_id,),
        ).fetchone()["cnt"]

        opportunities = []
        for row in high_cpa:
            opportunities.append({
                "type":  "budget",
                "icon":  "◎",
                "title": "Optimize Budget",
                "desc":  f"{row['campaign_name']} has elevated CPA — reallocate to top performers",
            })
        for row in best_ctr:
            opportunities.append({
                "type":  "scale",
                "icon":  "↑",
                "title": "Scale Winner",
                "desc":  f"{row['campaign_name']} is outperforming — increase budget to capture demand",
            })
        if content_pending > 0:
            opportunities.append({
                "type":  "content",
                "icon":  "◇",
                "title": f"{content_pending} Content Idea{'s' if content_pending != 1 else ''} Ready",
                "desc":  "Draft ideas awaiting approval in Content Studio",
            })
        if not opportunities:
            opportunities.append({
                "type":  "info",
                "icon":  "◈",
                "title": "System Analyzing",
                "desc":  "Keep running campaigns to unlock AI-powered opportunities",
            })

        # ── Account Health snapshot ───────────────────────────────────────────────
        acc_row = conn.execute(
            """
            SELECT account_name, platform, last_sync
            FROM ad_accounts
            WHERE status = 'active'
            ORDER BY is_default DESC, id ASC
            LIMIT 1
            """,
        ).fetchone()

        active_alert_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM alerts WHERE resolved = 0",
        ).fetchone()["cnt"]

        health = None
        if acc_row:
            sync_label = "Never"
            if acc_row["last_sync"]:
                try:
                    sync_dt = datetime.fromisoformat(acc_row["last_sync"])
                    delta = now - sync_dt
                    total_secs = int(delta.total_seconds())
                    if total_secs < 3600:
                        sync_label = f"{total_secs // 60}m ago"
                    elif delta.days == 0:
                        sync_label = f"{total_secs // 3600}h ago"
                    else:
                        sync_label = f"{delta.days}d ago"
                except Exception:
                    sync_label = str(acc_row["last_sync"])[:10]

            score = growth_score or 0
            if score >= 80:
                label = "Excellent"
            elif score >= 60:
                label = "Good"
            elif score >= 40:
                label = "Fair"
            else:
                label = "Needs Work"

            health = {
                "account_name": acc_row["account_name"],
                "platform":     acc_row["platform"],
                "score":        score,
                "label":        label,
                "spend_7d":     spend_7d,
                "conv_7d":      int(conv_7d),
                "last_sync":    sync_label,
                "alert_count":  active_alert_count,
            }

        return jsonify({
            "kpis": {
                "spend_7d":     spend_7d,
                "conv_7d":      int(conv_7d),
                "cpa_7d":       cpa_7d,
                "spend_today":  spend_today,
                "conv_today":   int(conv_today),
                "cpa_today":    cpa_today,
                "growth_score": growth_score,
                "growth_label": growth_label,
            },
            "attention": {
                "alerts":         [dict(a) for a in raw_alerts],
                "pending_auto":   pending_auto,
                "stale_accounts": stale_count,
            },
            "opportunities": opportunities,
            "health":        health,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
