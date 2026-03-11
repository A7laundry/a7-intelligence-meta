"""API routes — JSON endpoints for dashboard AJAX and future integrations."""

from flask import Blueprint, jsonify, request

from app.services.dashboard_service import DashboardService
from app.services.metrics_service import MetricsService
from app.services.snapshot_service import SnapshotService

api_bp = Blueprint("api", __name__)

_dashboard_service = None
_metrics_service = None


def _get_dashboard():
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardService()
    return _dashboard_service


def _get_metrics():
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service


# ── Dashboard Data ──────────────────────────────────────────

@api_bp.route("/dashboard/<range_key>")
def dashboard_data(range_key):
    """Get dashboard data for a specific range."""
    if range_key not in ("today", "7d", "30d"):
        return jsonify({"error": "Invalid range. Use: today, 7d, 30d"}), 400
    data = _get_dashboard().get_dashboard_data(range_key)
    return jsonify(data)


@api_bp.route("/dashboard/refresh", methods=["POST"])
def refresh_data():
    """Fetch fresh data from APIs and store snapshots."""
    data = _get_dashboard().fetch_and_store("today")
    return jsonify({"status": "ok", "data": data})


# ── Campaigns ───────────────────────────────────────────────

@api_bp.route("/campaigns")
def list_campaigns():
    """List all campaigns."""
    status = request.args.get("status")
    try:
        campaigns = _get_metrics().list_campaigns(status_filter=status)
    except Exception:
        campaigns = []
    return jsonify({"campaigns": campaigns})


@api_bp.route("/campaigns/<campaign_id>/adsets")
def list_ad_sets(campaign_id):
    """List ad sets for a campaign with insights."""
    period = request.args.get("period", "last_7d")
    ad_sets = _get_metrics().list_ad_sets(campaign_id)
    insights = _get_metrics().get_ad_set_insights(campaign_id, date_preset=period)

    # Merge insights into ad sets
    insights_map = {}
    for i in insights:
        adset_id = i.get("adset_id", "")
        insights_map[adset_id] = i

    enriched = []
    for adset in ad_sets:
        entry = {
            "id": adset["id"],
            "name": adset.get("name", ""),
            "status": adset.get("status", "UNKNOWN"),
        }
        ins = insights_map.get(adset["id"], {})
        if ins:
            entry["spend"] = float(ins.get("spend", 0))
            entry["impressions"] = int(ins.get("impressions", 0))
            entry["clicks"] = int(ins.get("clicks", 0))
            entry["ctr"] = round(float(ins.get("ctr", 0)), 2)
            # Extract conversions
            conversions = 0
            for a in ins.get("actions", []):
                if a.get("action_type") in ("onsite_conversion.messaging_first_reply", "lead"):
                    conversions += int(a.get("value", 0))
            entry["conversions"] = conversions
            entry["cpa"] = round(entry["spend"] / conversions, 2) if conversions > 0 else 0
        enriched.append(entry)

    return jsonify({"ad_sets": enriched})


@api_bp.route("/campaigns/<campaign_id>/status", methods=["POST"])
def update_campaign_status(campaign_id):
    """Update campaign status (ACTIVE/PAUSED)."""
    data = request.get_json()
    status = data.get("status", "").upper()
    if status not in ("ACTIVE", "PAUSED", "ARCHIVED"):
        return jsonify({"error": "Invalid status"}), 400
    result = _get_metrics().update_campaign_status(campaign_id, status)
    return jsonify(result)


@api_bp.route("/adsets/<ad_set_id>/status", methods=["POST"])
def update_ad_set_status(ad_set_id):
    """Update ad set status (ACTIVE/PAUSED)."""
    data = request.get_json()
    status = data.get("status", "").upper()
    if status not in ("ACTIVE", "PAUSED"):
        return jsonify({"error": "Invalid status"}), 400
    result = _get_metrics().update_ad_set_status(ad_set_id, status)
    return jsonify(result)


# ── History & Trends ────────────────────────────────────────

@api_bp.route("/history/daily")
def daily_history():
    """Get daily snapshots from database."""
    days = request.args.get("days", 30, type=int)
    platform = request.args.get("platform")
    snapshots = SnapshotService.get_daily_snapshots(platform=platform, days=days)
    return jsonify({"snapshots": snapshots})


@api_bp.route("/history/campaign/<campaign_id>")
def campaign_history(campaign_id):
    """Get historical data for a specific campaign."""
    days = request.args.get("days", 30, type=int)
    history = SnapshotService.get_campaign_history(campaign_id, days=days)
    return jsonify({"history": history})


@api_bp.route("/comparison")
def period_comparison():
    """Get period-over-period comparison."""
    days = request.args.get("days", 7, type=int)
    comparison = SnapshotService.get_period_comparison(days)
    return jsonify(comparison)


# ── System ──────────────────────────────────────────────────

@api_bp.route("/token/status")
def token_status():
    """Check Meta API token status."""
    result = _get_metrics().check_token()
    return jsonify(result)


@api_bp.route("/platforms")
def platform_status():
    """Check which platforms are connected."""
    svc = _get_dashboard()
    return jsonify({
        "meta": svc.meta_available,
        "google": svc.google_available,
    })


# ── Export ──────────────────────────────────────────────────

@api_bp.route("/export/campaigns.csv")
def export_campaigns_csv():
    """Export campaigns as CSV."""
    import csv
    import io
    from flask import Response

    range_key = request.args.get("range", "7d")
    data = _get_dashboard().get_dashboard_data(range_key)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Platform", "Campaign", "Status", "Spend", "Clicks", "CTR", "Conversions", "CPA", "ROAS"])

    for c in data.get("campaigns", {}).get("meta", []):
        writer.writerow(["Meta", c.get("name",""), c.get("status",""), c.get("spend",0),
                         c.get("clicks",0), c.get("ctr",0), c.get("conversions",0),
                         c.get("cpa",0), c.get("roas",0)])
    for c in data.get("campaigns", {}).get("google", []):
        writer.writerow(["Google", c.get("name",""), c.get("status",""), c.get("spend",0),
                         c.get("clicks",0), c.get("ctr",0), c.get("conversions",0),
                         c.get("cpa",0), c.get("roas",0)])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=a7-campaigns.csv"}
    )


# ── Observability ──────────────────────────────────────────

@api_bp.route("/stats")
def system_stats():
    """System statistics and observability."""
    from app.db.init_db import get_connection
    conn = get_connection()
    try:
        daily_count = conn.execute("SELECT COUNT(*) FROM daily_snapshots").fetchone()[0]
        campaign_count = conn.execute("SELECT COUNT(DISTINCT campaign_id) FROM campaign_snapshots").fetchone()[0]
        last_snapshot = conn.execute("SELECT MAX(created_at) FROM daily_snapshots").fetchone()[0]
        creative_count = 0
        try:
            creative_count = conn.execute("SELECT COUNT(*) FROM creatives").fetchone()[0]
        except:
            pass
        return jsonify({
            "daily_snapshots": daily_count,
            "campaigns_tracked": campaign_count,
            "creatives_tracked": creative_count,
            "last_snapshot": last_snapshot,
        })
    finally:
        conn.close()
