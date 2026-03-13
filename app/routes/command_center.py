"""Command Center API — single endpoint aggregating all Overview page data.

KPI Strategy:
  - Primary: daily_snapshots (fast, no API call, powers trend charts)
  - Fallback: DashboardService live data when snapshots are sparse (<3 days)
  - `kpi_source` field tells the UI which source is in use
  - When using live data, `partial` flag is set so UI can label accordingly
"""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from app.db.init_db import get_connection

cc_bp = Blueprint("command_center", __name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pct(curr, prev):
    """Return percent change or None when prev is zero/None."""
    if not prev:
        return None
    return round((curr - prev) / prev * 100, 1)


def _safe_float(v, digits=2):
    try:
        return round(float(v), digits) if v is not None else None
    except (TypeError, ValueError):
        return None


# ── Live KPI fallback ─────────────────────────────────────────────────────────

def _get_live_kpis(account_id: int) -> dict:
    """
    Fetch 7-day KPIs from DashboardService (live Meta API).
    Returns a dict with the same keys as the snapshot-based aggregation,
    plus meta about the source. Returns empty-safe dict on failure.
    """
    empty = {
        "spend_7d": 0, "conv_7d": 0, "clicks_7d": 0, "impressions_7d": 0,
        "cpa_7d": None, "ctr_7d": None, "cpc_7d": None, "live": True,
    }
    try:
        from app.services.dashboard_service import DashboardService
        svc = DashboardService()
        data = svc.build_payload("7d", account_id=account_id)
        total = data.get("summary", {}).get("total", {})
        spend = float(total.get("spend", 0) or 0)
        conv  = int(total.get("conversions", 0) or 0)
        clk   = int(total.get("clicks", 0) or 0)
        imp   = int(total.get("impressions", 0) or 0)
        return {
            "spend_7d":       round(spend, 2),
            "conv_7d":        conv,
            "clicks_7d":      clk,
            "impressions_7d": imp,
            "cpa_7d":         _safe_float(spend / conv) if conv > 0 else None,
            "ctr_7d":         _safe_float(clk / imp * 100) if imp > 0 else None,
            "cpc_7d":         _safe_float(spend / clk) if clk > 0 else None,
            "live":           True,
        }
    except Exception:
        return empty


# ── Insight Engine ────────────────────────────────────────────────────────────

def _build_insights(kpis, prev, top_camps, camp_dist, sev_map, trend):
    """
    Generate 3-5 prioritised, actionable insights from real account data.
    Each insight is purely rule-based — no generative AI, no invented text.
    Returns list sorted by priority (highest first), capped at 5.
    """
    insights = []

    spend_c = kpis["spend_7d"]
    conv_c  = kpis["conv_7d"]
    cpa_c   = kpis["cpa_7d"]
    ctr_c   = kpis["ctr_7d"]
    cpc_c   = kpis["cpc_7d"]

    spend_p = prev["spend"]
    conv_p  = prev["conversions"]
    cpa_p   = prev["cpa"]
    ctr_p   = prev["ctr"]
    cpc_p   = prev["cpc"]

    spend_ch = _pct(spend_c, spend_p)
    conv_ch  = _pct(conv_c,  conv_p)
    cpa_ch   = _pct(cpa_c,   cpa_p)  if cpa_c  and cpa_p  else None
    ctr_ch   = _pct(ctr_c,   ctr_p)  if ctr_c  and ctr_p  else None
    cpc_ch   = _pct(cpc_c,   cpc_p)  if cpc_c  and cpc_p  else None

    # ── Rule 1: Spend-Conversion Divergence ──────────────────────────────────
    if spend_ch is not None and conv_ch is not None:
        if spend_ch > 10 and conv_ch < -5:
            insights.append({
                "rule_type":    "spend_conv_divergence_neg",
                "signal":       "negative", "priority": 9,
                "title":        f"Spend +{spend_ch:.0f}% while Conversions {conv_ch:.0f}%",
                "body":         f"Efficiency declining — ${spend_c:.0f} spent for {int(conv_c)} conversions.",
                "metric":       f"${cpa_c:.2f} CPA" if cpa_c else f"+{spend_ch:.0f}% spend",
                "action_label": "Review Budget", "action_page": "budget",
            })
        elif spend_ch < -10 and conv_ch > 5:
            insights.append({
                "rule_type":    "spend_conv_divergence_pos",
                "signal":       "positive", "priority": 6,
                "title":        f"Less spend (−{abs(spend_ch):.0f}%), more conversions (+{conv_ch:.0f}%)",
                "body":         f"Efficiency improving. ${spend_c:.0f} drove {int(conv_c)} conversions.",
                "metric":       f"${cpa_c:.2f} CPA" if cpa_c else f"+{conv_ch:.0f}% conv",
                "action_label": "Scale Winners", "action_page": "campaigns",
            })

    # ── Rule 2: CPA Drift ────────────────────────────────────────────────────
    if cpa_ch is not None:
        if cpa_ch > 20:
            insights.append({
                "rule_type":    "cpa_drift_neg",
                "signal":       "negative", "priority": 8,
                "title":        f"CPA worsened +{cpa_ch:.0f}% vs prior 7 days",
                "body":         f"Cost per acquisition rose from ${cpa_p:.2f} → ${cpa_c:.2f}.",
                "metric":       f"${cpa_c:.2f} CPA",
                "action_label": "Optimise Campaigns", "action_page": "campaigns",
            })
        elif cpa_ch < -15:
            insights.append({
                "rule_type":    "cpa_drift_pos",
                "signal":       "positive", "priority": 5,
                "title":        f"CPA improved {abs(cpa_ch):.0f}% — efficiency gaining",
                "body":         f"From ${cpa_p:.2f} → ${cpa_c:.2f}. Consider scaling budget.",
                "metric":       f"${cpa_c:.2f} CPA",
                "action_label": "Increase Budget", "action_page": "budget",
            })

    # ── Rule 3: CTR Trend ────────────────────────────────────────────────────
    if ctr_ch is not None:
        if ctr_ch < -15:
            insights.append({
                "rule_type":    "ctr_fatigue",
                "signal":       "warning", "priority": 7,
                "title":        f"CTR dropped {abs(ctr_ch):.0f}% — possible creative fatigue",
                "body":         f"Engagement declining: {ctr_c:.2f}% CTR (was {ctr_p:.2f}%). Refresh creatives.",
                "metric":       f"{ctr_c:.2f}% CTR",
                "action_label": "Refresh Creatives", "action_page": "creative",
            })
        elif ctr_ch > 20:
            insights.append({
                "rule_type":    "ctr_resonance",
                "signal":       "positive", "priority": 4,
                "title":        f"CTR up +{ctr_ch:.0f}% — creative resonating",
                "body":         f"Audience engagement strong: {ctr_c:.2f}% CTR (was {ctr_p:.2f}%).",
                "metric":       f"{ctr_c:.2f}% CTR",
                "action_label": "View Creatives", "action_page": "creative",
            })

    # ── Rule 4: CPC Surge ────────────────────────────────────────────────────
    if cpc_ch is not None and cpc_ch > 25:
        insights.append({
            "rule_type":    "cpc_surge",
            "signal":       "warning", "priority": 6,
            "title":        f"CPC up +{cpc_ch:.0f}% — auction competition rising",
            "body":         f"Cost-per-click: ${cpc_c:.2f} (was ${cpc_p:.2f}). Review bid strategy.",
            "metric":       f"${cpc_c:.2f} CPC",
            "action_label": "Review Bids", "action_page": "budget",
        })

    # ── Rule 5: Budget Concentration Risk ────────────────────────────────────
    if top_camps and spend_c > 0:
        top_spend = top_camps[0]["spend"]
        share = top_spend / spend_c
        if share > 0.65:
            insights.append({
                "rule_type":    "budget_concentration",
                "signal":       "warning", "priority": 5,
                "title":        f"Top campaign holds {share * 100:.0f}% of account spend",
                "body":         f"'{top_camps[0]['name']}' — ${top_spend:.0f} of ${spend_c:.0f}. Concentration risk.",
                "metric":       f"{share * 100:.0f}% share",
                "action_label": "Rebalance Budget", "action_page": "budget",
            })

    # ── Rule 6: Delivery Risk ────────────────────────────────────────────────
    active = camp_dist.get("active", 0)
    paused = camp_dist.get("paused", 0)
    total  = camp_dist.get("total",  0)
    if total > 0:
        if active == 0:
            insights.append({
                "rule_type":    "no_active_campaigns",
                "signal":       "critical", "priority": 10,
                "title":        "No active campaigns — account delivery halted",
                "body":         f"All {paused} campaign{'s' if paused != 1 else ''} paused. No reach.",
                "metric":       f"{paused} paused",
                "action_label": "Activate Campaigns", "action_page": "campaigns",
            })
        elif paused > active and paused > 2:
            insights.append({
                "rule_type":    "majority_paused",
                "signal":       "warning", "priority": 6,
                "title":        f"{paused} campaigns paused, only {active} running",
                "body":         "Majority of campaigns paused — potential reach is limited.",
                "metric":       f"{active}/{total} running",
                "action_label": "Review Campaigns", "action_page": "campaigns",
            })

    # ── Rule 7: Alert Severity Spike ─────────────────────────────────────────
    crit_n = sev_map.get("critical", 0)
    warn_n = sev_map.get("warning", 0)
    if crit_n > 0:
        insights.append({
            "rule_type":    "critical_alerts",
            "signal":       "critical", "priority": 10,
            "title":        f"{crit_n} critical alert{'s' if crit_n > 1 else ''} require immediate action",
            "body":         "Critical issues can halt delivery, waste budget, or violate policy.",
            "metric":       f"{crit_n} critical",
            "action_label": "View Alerts", "action_page": "alerts",
        })
    elif warn_n > 3:
        insights.append({
            "rule_type":    "warning_cluster",
            "signal":       "warning", "priority": 5,
            "title":        f"{warn_n} active warnings — systemic issues likely",
            "body":         "Multiple warnings often signal structural inefficiency.",
            "metric":       f"{warn_n} warnings",
            "action_label": "View Alerts", "action_page": "alerts",
        })

    # ── Rule 8: Zero-Conversion Window ────────────────────────────────────────
    recent = trend[-3:] if len(trend) >= 3 else trend
    recent_conv  = sum(d["conversions"] for d in recent)
    recent_spend = sum(d["spend"] for d in recent)
    if recent_conv == 0 and recent_spend > 5:
        insights.append({
            "rule_type":    "zero_conv_window",
            "signal":       "critical", "priority": 9,
            "title":        f"0 conversions in last 3 days despite ${recent_spend:.0f} spend",
            "body":         "Conversion tracking may be broken, or targeting needs adjustment.",
            "metric":       f"${recent_spend:.0f} at risk",
            "action_label": "Check Tracking", "action_page": "ai-coach",
        })

    # ── Rule 9: Worst Performer ───────────────────────────────────────────────
    if not any(i["action_page"] == "campaigns" and i["signal"] == "negative" for i in insights):
        worst = None
        if kpis.get("worst_campaigns"):
            worst = kpis["worst_campaigns"][0]
        if worst and cpa_c and worst["cpa"] > cpa_c * 2 and worst["spend"] > 20:
            insights.append({
                "rule_type":    "worst_performer",
                "signal":       "negative", "priority": 7,
                "title":        "Worst performer draining efficiency",
                "body":         f"'{worst['name']}' — ${worst['cpa']:.2f} CPA vs ${cpa_c:.2f} avg. Review or pause.",
                "metric":       f"${worst['cpa']:.2f} CPA",
                "action_label": "Pause Campaign", "action_page": "campaigns",
            })

    # ── Rule 10: Positive Momentum ────────────────────────────────────────────
    gs = kpis.get("growth_score")
    if gs and gs >= 75 and conv_ch and conv_ch > 0:
        if not any(i["signal"] in ("negative", "critical") for i in insights):
            insights.append({
                "rule_type":    "positive_momentum",
                "signal":       "positive", "priority": 3,
                "title":        f"Account performing well — Growth Score {gs:.0f}",
                "body":         f"Conversions +{conv_ch:.0f}% vs prior period. Keep current strategy.",
                "metric":       f"Score {gs:.0f}",
                "action_label": "Scale Up", "action_page": "budget",
            })

    insights.sort(key=lambda x: x["priority"], reverse=True)
    return insights[:5]


# ── Route ────────────────────────────────────────────────────────────────────

@cc_bp.route("/command-center")
def command_center():
    account_id = request.args.get("account_id", type=int) or 1

    conn = get_connection()
    try:
        now               = datetime.utcnow()
        today_str         = now.strftime("%Y-%m-%d")
        seven_days_ago    = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        fourteen_days_ago = (now - timedelta(days=14)).strftime("%Y-%m-%d")

        # ── Snapshot row count (determines if we use live fallback) ───────────
        snap_days = conn.execute(
            "SELECT COUNT(DISTINCT date) FROM daily_snapshots WHERE date >= ? AND account_id = ?",
            (seven_days_ago, account_id),
        ).fetchone()[0]

        kpi_source = "snapshots"

        # ── KPIs: current 7-day window ────────────────────────────────────────
        kpi = conn.execute(
            """
            SELECT
                COALESCE(SUM(spend), 0)       AS spend_7d,
                COALESCE(SUM(conversions), 0) AS conv_7d,
                COALESCE(SUM(clicks), 0)      AS clicks_7d,
                COALESCE(SUM(impressions), 0) AS impressions_7d
            FROM daily_snapshots
            WHERE date >= ? AND account_id = ?
            """,
            (seven_days_ago, account_id),
        ).fetchone()

        spend_7d       = float(kpi["spend_7d"] or 0)
        conv_7d        = int(kpi["conv_7d"] or 0)
        clicks_7d      = int(kpi["clicks_7d"] or 0)
        impressions_7d = int(kpi["impressions_7d"] or 0)

        # ── Live fallback when snapshots are sparse (<3 days) ────────────────
        if snap_days < 3:
            live = _get_live_kpis(account_id)
            spend_7d       = live["spend_7d"]
            conv_7d        = live["conv_7d"]
            clicks_7d      = live["clicks_7d"]
            impressions_7d = live["impressions_7d"]
            kpi_source     = "live"

        cpa_7d = _safe_float(spend_7d / conv_7d)       if conv_7d        > 0 else None
        ctr_7d = _safe_float(clicks_7d / impressions_7d * 100) if impressions_7d > 0 else None
        cpc_7d = _safe_float(spend_7d / clicks_7d)     if clicks_7d      > 0 else None

        # ── KPIs: previous 7-day window (days 8–14 ago) ──────────────────────
        kpi_prev = conn.execute(
            """
            SELECT
                COALESCE(SUM(spend), 0)       AS spend,
                COALESCE(SUM(conversions), 0) AS conversions,
                COALESCE(SUM(clicks), 0)      AS clicks,
                COALESCE(SUM(impressions), 0) AS impressions
            FROM daily_snapshots
            WHERE date >= ? AND date < ? AND account_id = ?
            """,
            (fourteen_days_ago, seven_days_ago, account_id),
        ).fetchone()

        prev_spend = float(kpi_prev["spend"] or 0)
        prev_conv  = int(kpi_prev["conversions"] or 0)
        prev_clk   = int(kpi_prev["clicks"] or 0)
        prev_imp   = int(kpi_prev["impressions"] or 0)
        prev_cpa   = _safe_float(prev_spend / prev_conv) if prev_conv > 0 else None
        prev_ctr   = _safe_float(prev_clk / prev_imp * 100) if prev_imp > 0 else None
        prev_cpc   = _safe_float(prev_spend / prev_clk)  if prev_clk > 0 else None

        period_comparison = {
            "current":  {"spend": spend_7d, "conversions": conv_7d, "cpa": cpa_7d, "ctr": ctr_7d, "cpc": cpc_7d},
            "previous": {"spend": prev_spend, "conversions": prev_conv, "cpa": prev_cpa, "ctr": prev_ctr, "cpc": prev_cpc},
            "changes": {
                "spend":       _pct(spend_7d, prev_spend),
                "conversions": _pct(conv_7d,  prev_conv),
                "cpa":         _pct(cpa_7d,   prev_cpa) if cpa_7d and prev_cpa else None,
                "ctr":         _pct(ctr_7d,   prev_ctr) if ctr_7d and prev_ctr else None,
                "cpc":         _pct(cpc_7d,   prev_cpc) if cpc_7d and prev_cpc else None,
            },
        }

        # ── KPIs: today ───────────────────────────────────────────────────────
        kpi_today = conn.execute(
            """
            SELECT COALESCE(SUM(spend),0) AS spend_today,
                   COALESCE(SUM(conversions),0) AS conv_today
            FROM daily_snapshots
            WHERE date = ? AND account_id = ?
            """,
            (today_str, account_id),
        ).fetchone()
        spend_today = float(kpi_today["spend_today"] or 0)
        conv_today  = int(kpi_today["conv_today"] or 0)
        cpa_today   = _safe_float(spend_today / conv_today) if conv_today > 0 else None

        # ── Growth Score ──────────────────────────────────────────────────────
        growth_score = None
        growth_label = None
        try:
            from app.services.growth_score_service import GrowthScoreService
            gs_result    = GrowthScoreService().build_growth_score(days=7, account_id=account_id)
            growth_score = gs_result.get("score")
            growth_label = gs_result.get("label")
        except Exception:
            pass

        # ── Alerts ────────────────────────────────────────────────────────────
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

        active_alert_count = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE resolved = 0 AND account_id = ?",
            (account_id,),
        ).fetchone()[0]

        # ── Alert severity breakdown ──────────────────────────────────────────
        sev_counts = conn.execute(
            "SELECT severity, COUNT(*) AS cnt FROM alerts WHERE resolved = 0 AND account_id = ? GROUP BY severity",
            (account_id,),
        ).fetchall()
        sev_map = {r["severity"]: r["cnt"] for r in sev_counts}

        # ── Pending automation ────────────────────────────────────────────────
        pending_auto = conn.execute(
            "SELECT COUNT(*) FROM automation_actions WHERE status = 'proposed' AND account_id = ?",
            (account_id,),
        ).fetchone()[0]

        # ── Stale connectors ──────────────────────────────────────────────────
        stale_thresh = (now - timedelta(hours=24)).isoformat()
        stale_count = conn.execute(
            "SELECT COUNT(*) FROM ad_accounts WHERE status = 'active' AND (last_sync IS NULL OR last_sync < ?)",
            (stale_thresh,),
        ).fetchone()[0]

        # ── Daily trend (7 days) ──────────────────────────────────────────────
        raw_trend = conn.execute(
            """
            SELECT date,
                   COALESCE(SUM(spend), 0)       AS spend,
                   COALESCE(SUM(conversions), 0) AS conversions,
                   COALESCE(SUM(clicks), 0)      AS clicks,
                   COALESCE(SUM(impressions), 0) AS impressions
            FROM daily_snapshots
            WHERE date >= ? AND account_id = ?
            GROUP BY date ORDER BY date ASC
            """,
            (seven_days_ago, account_id),
        ).fetchall()
        trend_by_date = {r["date"]: r for r in raw_trend}
        trend = []
        for i in range(7):
            d   = (now - timedelta(days=6 - i)).strftime("%Y-%m-%d")
            row = trend_by_date.get(d)
            imp = float(row["impressions"]) if row else 0
            clk = float(row["clicks"])      if row else 0
            spd = float(row["spend"])       if row else 0
            trend.append({
                "date":        d,
                "spend":       round(spd, 2),
                "conversions": int(row["conversions"]) if row else 0,
                "clicks":      int(clk),
                "ctr":         round(clk / imp * 100, 2) if imp > 0 else 0,
                "cpc":         round(spd / clk, 2)        if clk > 0 else 0,
                "has_data":    row is not None,
            })
        trend_days_available = sum(1 for t in trend if t["has_data"])

        # ── Top 5 campaigns by spend ──────────────────────────────────────────
        top_camps_rows = conn.execute(
            """
            SELECT campaign_name,
                   SUM(spend)       AS total_spend,
                   SUM(conversions) AS total_conv,
                   CASE WHEN SUM(conversions) > 0
                        THEN ROUND(SUM(spend) / SUM(conversions), 2)
                        ELSE 0 END  AS cpa,
                   MAX(status)      AS status
            FROM campaign_snapshots
            WHERE date >= ? AND account_id = ?
            GROUP BY campaign_id
            ORDER BY total_spend DESC
            LIMIT 5
            """,
            (seven_days_ago, account_id),
        ).fetchall()
        top_camps = [
            {
                "name":   r["campaign_name"],
                "spend":  round(float(r["total_spend"]), 2),
                "conv":   int(r["total_conv"]),
                "cpa":    round(float(r["cpa"]), 2),
                "status": r["status"],
            }
            for r in top_camps_rows
        ]

        # ── Worst performers by CPA ───────────────────────────────────────────
        worst_camps = conn.execute(
            """
            SELECT campaign_name,
                   SUM(spend)       AS total_spend,
                   SUM(conversions) AS total_conv,
                   ROUND(SUM(spend) / SUM(conversions), 2) AS cpa,
                   MAX(status)      AS status
            FROM campaign_snapshots
            WHERE date >= ? AND account_id = ? AND conversions > 0
            GROUP BY campaign_id HAVING SUM(conversions) > 0
            ORDER BY cpa DESC LIMIT 5
            """,
            (seven_days_ago, account_id),
        ).fetchall()

        # ── Campaign distribution ─────────────────────────────────────────────
        dist = conn.execute(
            """
            SELECT status, COUNT(DISTINCT campaign_id) AS cnt
            FROM campaign_snapshots
            WHERE date >= ? AND account_id = ?
            GROUP BY status
            """,
            (seven_days_ago, account_id),
        ).fetchall()
        dist_map   = {r["status"]: r["cnt"] for r in dist}
        active_cnt = dist_map.get("ACTIVE", 0)
        paused_cnt = dist_map.get("PAUSED", 0)
        total_cnt  = sum(dist_map.values())

        # ── Opportunities (legacy block) ──────────────────────────────────────
        high_cpa = conn.execute(
            """
            SELECT campaign_name, AVG(cpa) AS avg_cpa
            FROM campaign_snapshots
            WHERE date >= ? AND cpa > 0 AND account_id = ?
            GROUP BY campaign_id ORDER BY avg_cpa DESC LIMIT 2
            """,
            (seven_days_ago, account_id),
        ).fetchall()
        best_ctr = conn.execute(
            """
            SELECT campaign_name, AVG(ctr) AS avg_ctr
            FROM campaign_snapshots
            WHERE date >= ? AND ctr > 0 AND account_id = ?
            GROUP BY campaign_id ORDER BY avg_ctr DESC LIMIT 1
            """,
            (seven_days_ago, account_id),
        ).fetchall()
        content_pending = conn.execute(
            "SELECT COUNT(*) FROM content_ideas WHERE status IN ('idea', 'draft') AND account_id = ?",
            (account_id,),
        ).fetchone()[0]

        opportunities = []
        for row in high_cpa:
            opportunities.append({
                "type": "budget", "icon": "◎", "title": "Optimize Budget",
                "desc": f"{row['campaign_name']} has elevated CPA — reallocate to top performers",
            })
        for row in best_ctr:
            opportunities.append({
                "type": "scale", "icon": "↑", "title": "Scale Winner",
                "desc": f"{row['campaign_name']} is outperforming — increase budget to capture demand",
            })
        if content_pending > 0:
            opportunities.append({
                "type": "content", "icon": "◇",
                "title": f"{content_pending} Content Idea{'s' if content_pending != 1 else ''} Ready",
                "desc": "Draft ideas awaiting approval in Content Studio",
            })
        if not opportunities:
            opportunities.append({
                "type": "info", "icon": "◈", "title": "System Analysing",
                "desc": "Keep running campaigns to unlock AI-powered opportunities",
            })

        # ── Account Health (FIXED: always use requested account_id) ──────────
        acc_row = conn.execute(
            "SELECT account_name, platform, last_sync FROM ad_accounts WHERE id = ? AND status = 'active' LIMIT 1",
            (account_id,),
        ).fetchone()

        # Fallback: fetch account regardless of active status but still filter by id
        if not acc_row:
            acc_row = conn.execute(
                "SELECT account_name, platform, last_sync FROM ad_accounts WHERE id = ? LIMIT 1",
                (account_id,),
            ).fetchone()

        health = None
        if acc_row:
            sync_label = "Never"
            if acc_row["last_sync"]:
                try:
                    sync_dt    = datetime.fromisoformat(acc_row["last_sync"].replace("Z", "+00:00").replace("+00:00", ""))
                    delta      = now - sync_dt
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
            label = (
                "Excellent" if score >= 80 else
                "Good"      if score >= 60 else
                "Fair"      if score >= 40 else
                "Needs Work"
            )
            health = {
                "account_name": acc_row["account_name"],   # ← always the requested account
                "platform":     acc_row["platform"],
                "score":        score,
                "label":        label,
                "spend_7d":     spend_7d,
                "conv_7d":      conv_7d,
                "last_sync":    sync_label,
                "alert_count":  active_alert_count,
            }

        # ── Insight Engine ────────────────────────────────────────────────────
        kpis_for_insights = {
            "spend_7d":        spend_7d,
            "conv_7d":         conv_7d,
            "cpa_7d":          cpa_7d,
            "ctr_7d":          ctr_7d,
            "cpc_7d":          cpc_7d,
            "growth_score":    growth_score,
            "worst_campaigns": [
                {"name": r["campaign_name"], "cpa": float(r["cpa"]), "spend": float(r["total_spend"])}
                for r in worst_camps
            ],
        }
        prev_for_insights = {
            "spend":       prev_spend,
            "conversions": prev_conv,
            "cpa":         prev_cpa,
            "ctr":         prev_ctr,
            "cpc":         prev_cpc,
        }
        camp_dist_for_insights = {"active": active_cnt, "paused": paused_cnt, "total": total_cnt}

        insights = _build_insights(
            kpis_for_insights, prev_for_insights,
            top_camps, camp_dist_for_insights, sev_map, trend,
        )

        # Persist insights and enrich with state metadata
        try:
            from app.services.pulse_service import PulseService
            insights = PulseService.upsert_insights(account_id, insights)
        except Exception:
            pass  # Never fail the main endpoint if persistence blows up

        return jsonify({
            "kpis": {
                "spend_7d":       spend_7d,
                "conv_7d":        conv_7d,
                "cpa_7d":         cpa_7d,
                "ctr_7d":         ctr_7d,
                "cpc_7d":         cpc_7d,
                "clicks_7d":      clicks_7d,
                "impressions_7d": impressions_7d,
                "spend_today":    spend_today,
                "conv_today":     conv_today,
                "cpa_today":      cpa_today,
                "growth_score":   growth_score,
                "growth_label":   growth_label,
            },
            "kpi_source":            kpi_source,
            "trend_days_available":  trend_days_available,
            "period_comparison":     period_comparison,
            "insights":              insights,
            "trend":                 trend,
            "top_campaigns":         top_camps,
            "worst_campaigns": [
                {
                    "name":  r["campaign_name"],
                    "spend": round(float(r["total_spend"]), 2),
                    "conv":  int(r["total_conv"]),
                    "cpa":   round(float(r["cpa"]), 2),
                }
                for r in worst_camps
            ],
            "campaign_distribution": {
                "active": active_cnt,
                "paused": paused_cnt,
                "total":  total_cnt,
            },
            "alert_severity": sev_map,
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
