"""Dashboard routes — serves the main dashboard UI."""

from flask import Blueprint, render_template, request

from app.services.dashboard_service import DashboardService

dashboard_bp = Blueprint("dashboard", __name__)

_service = None


def _get_service():
    global _service
    if _service is None:
        _service = DashboardService()
    return _service


@dashboard_bp.route("/")
def index():
    """Main dashboard page."""
    range_key = request.args.get("range", "7d")
    if range_key not in ("today", "7d", "30d"):
        range_key = "7d"
    return render_template("dashboard.html", current_range=range_key)
