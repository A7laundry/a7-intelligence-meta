"""Report export routes — PDF and CSV downloads."""
from flask import Blueprint, request, Response
from app.services.account_service import AccountService

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports/export/csv")
def export_csv():
    """Download CSV performance report."""
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    days = request.args.get("days", 30, type=int)

    from app.services.reporting_service import ReportingService
    csv_bytes = ReportingService.export_account_csv(account_id, days)

    from datetime import datetime
    filename = f"a7-report-{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@reports_bp.route("/reports/export/pdf")
def export_pdf():
    """Download PDF performance report."""
    account_id = AccountService.resolve_account_id(request.args.get("account_id"))
    days = request.args.get("days", 30, type=int)

    try:
        account = AccountService.get_account(account_id)
        account_name = account.get("account_name", "Account") if account else "Account"
    except Exception:
        account_name = "Account"

    from app.services.reporting_service import ReportingService
    pdf_bytes = ReportingService.export_account_pdf(account_id, days, account_name)

    from datetime import datetime
    filename = f"a7-report-{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
