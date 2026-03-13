"""Analytics & Reports API routes."""

from flask import Blueprint, jsonify, request, Response
from app.services.account_service import AccountService

analytics_reports_bp = Blueprint("analytics_reports", __name__)

_analytics_svc = None
_reporting_svc = None


def _get_analytics():
    global _analytics_svc
    if _analytics_svc is None:
        from app.services.advanced_analytics_service import AdvancedAnalyticsService
        _analytics_svc = AdvancedAnalyticsService()
    return _analytics_svc


def _get_reporting():
    global _reporting_svc
    if _reporting_svc is None:
        from app.services.reporting_service import ReportingService
        _reporting_svc = ReportingService()
    return _reporting_svc


# ── Analytics ──────────────────────────────────────────────

@analytics_reports_bp.route("/analytics/baselines")
def analytics_baselines():
    """Get statistical baselines for all key metrics."""
    days = request.args.get("days", 30, type=int)
    platform = request.args.get("platform")
    return jsonify(_get_analytics().calculate_all_baselines(days, platform))


@analytics_reports_bp.route("/analytics/anomalies")
def analytics_anomalies():
    """Detect anomalies across all key metrics."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    return jsonify(_get_analytics().detect_all_anomalies(days, platform))


@analytics_reports_bp.route("/analytics/anomalies/<metric>")
def analytics_metric_anomalies(metric):
    """Detect anomalies for a specific metric."""
    valid = {"spend", "conversions", "cpa", "ctr", "clicks", "impressions"}
    if metric not in valid:
        return jsonify({"error": f"Invalid metric. Use: {', '.join(sorted(valid))}"}), 400
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    return jsonify(_get_analytics().detect_metric_anomalies(metric, days, platform))


@analytics_reports_bp.route("/analytics/forecast")
def analytics_forecast():
    """Forecast all key metrics."""
    horizon = request.args.get("horizon", 7, type=int)
    platform = request.args.get("platform")
    return jsonify(_get_analytics().forecast_all_metrics(horizon, platform))


@analytics_reports_bp.route("/analytics/forecast/<metric>")
def analytics_metric_forecast(metric):
    """Forecast a specific metric."""
    valid = {"spend", "conversions", "cpa", "ctr", "clicks", "impressions"}
    if metric not in valid:
        return jsonify({"error": f"Invalid metric. Use: {', '.join(sorted(valid))}"}), 400
    horizon = request.args.get("horizon", 7, type=int)
    platform = request.args.get("platform")
    return jsonify(_get_analytics().forecast_metric(metric, horizon, platform))


# ── Reports ────────────────────────────────────────────────

@analytics_reports_bp.route("/reports/latest")
def report_latest():
    """Get the latest executive report as JSON."""
    days = request.args.get("days", 7, type=int)
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    return jsonify(_get_reporting().generate_executive_report(days, account_id=account_id))


@analytics_reports_bp.route("/reports/generate")
def report_generate():
    """Generate a fresh executive report."""
    days = request.args.get("days", 7, type=int)
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    return jsonify(_get_reporting().generate_executive_report(days, account_id=account_id))


@analytics_reports_bp.route("/reports/export/json")
def report_export_json():
    """Export report as downloadable JSON."""
    days = request.args.get("days", 7, type=int)
    content = _get_reporting().export_json(days)
    return Response(
        content,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=a7-executive-report.json"},
    )


@analytics_reports_bp.route("/reports/export/csv")
def report_export_csv():
    """Export report as downloadable CSV."""
    days = request.args.get("days", 7, type=int)
    content = _get_reporting().export_csv(days)
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=a7-executive-report.csv"},
    )


@analytics_reports_bp.route("/reports/export/pdf")
def report_export_pdf():
    """Export report as downloadable PDF."""
    days = request.args.get("days", 7, type=int)
    content = _get_reporting().export_pdf(days)
    return Response(
        content,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=a7-executive-report.pdf"},
    )
