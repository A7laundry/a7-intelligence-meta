"""Reporting Service — Executive report generation and export.

Produces structured executive reports combining all intelligence modules,
with export to JSON, CSV, and PDF formats.

TODO: Add LLM narrative generation for richer executive summaries
TODO: Add automated weekly report scheduling
TODO: Add email delivery integration
TODO: Add Slack summary delivery
"""

import csv
import io
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class ReportingService:
    """Generates and exports executive marketing reports."""

    def generate_executive_report(self, days=7):
        """Generate a comprehensive executive report combining all intelligence modules."""
        now = datetime.utcnow()
        report = {
            "title": "A7 Intelligence — Executive Report",
            "period_days": days,
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generated_date": now.strftime("%Y-%m-%d"),
            "sections": {},
        }

        # 1. Executive Summary
        report["sections"]["executive_summary"] = self._build_executive_summary(days)

        # 2. Growth Score
        report["sections"]["growth_score"] = self._get_growth_score(days)

        # 3. Platform Comparison
        report["sections"]["platform_comparison"] = self._get_platform_comparison(days)

        # 4. Top Performing Campaigns
        report["sections"]["top_campaigns"] = self._get_top_campaigns(days)

        # 5. Biggest Risks
        report["sections"]["risks"] = self._get_risks(days)

        # 6. Key Opportunities
        report["sections"]["opportunities"] = self._get_opportunities(days)

        # 7. Forecast Summary
        report["sections"]["forecast"] = self._get_forecast_summary(days)

        # 8. Alert Summary
        report["sections"]["alert_summary"] = self._get_alert_summary()

        return report

    def export_json(self, days=7):
        """Export report as JSON string."""
        report = self.generate_executive_report(days)
        return json.dumps(report, indent=2, default=str)

    def export_csv(self, days=7):
        """Export report as CSV with key metrics."""
        report = self.generate_executive_report(days)
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["A7 Intelligence Executive Report"])
        writer.writerow(["Period", f"{days} days"])
        writer.writerow(["Generated", report["generated_at"]])
        writer.writerow([])

        # Executive Summary
        summary = report["sections"].get("executive_summary", {})
        writer.writerow(["== Executive Summary =="])
        writer.writerow(["Total Spend", summary.get("total_spend", 0)])
        writer.writerow(["Total Conversions", summary.get("total_conversions", 0)])
        writer.writerow(["Average CPA", summary.get("avg_cpa", 0)])
        writer.writerow(["Average CTR", summary.get("avg_ctr", 0)])
        writer.writerow([])

        # Growth Score
        gs = report["sections"].get("growth_score", {})
        writer.writerow(["== Growth Score =="])
        writer.writerow(["Score", gs.get("score", 0)])
        writer.writerow(["Label", gs.get("label", "unknown")])
        writer.writerow(["Summary", gs.get("summary", "")])
        writer.writerow([])

        # Platform Comparison
        pc = report["sections"].get("platform_comparison", {})
        platforms = pc.get("platforms", [])
        if platforms:
            writer.writerow(["== Platform Comparison =="])
            writer.writerow(["Platform", "Spend", "Conversions", "CPA", "CTR", "Share"])
            for p in platforms:
                writer.writerow([
                    p.get("platform", ""),
                    p.get("spend", 0),
                    p.get("conversions", 0),
                    p.get("avg_cpa", 0),
                    p.get("ctr", 0),
                    f"{p.get('share_of_spend', 0)}%",
                ])
            writer.writerow([])

        # Top Campaigns
        tc = report["sections"].get("top_campaigns", {})
        campaigns = tc.get("campaigns", [])
        if campaigns:
            writer.writerow(["== Top Campaigns =="])
            writer.writerow(["Campaign", "Platform", "Spend", "Conversions", "CPA"])
            for c in campaigns[:10]:
                writer.writerow([
                    c.get("campaign_name", ""),
                    c.get("platform", ""),
                    c.get("spend", 0),
                    c.get("conversions", 0),
                    c.get("cpa", 0),
                ])
            writer.writerow([])

        # Forecast
        fc = report["sections"].get("forecast", {})
        forecasts = fc.get("forecasts", {})
        if forecasts:
            writer.writerow(["== Forecasts =="])
            writer.writerow(["Metric", "Current", "Forecast End", "Trend", "Confidence"])
            for metric, data in forecasts.items():
                writer.writerow([
                    metric,
                    data.get("current_value", 0),
                    data.get("forecast_end_value", 0),
                    data.get("trend_direction", ""),
                    data.get("confidence", ""),
                ])

        return output.getvalue()

    def export_pdf(self, days=7):
        """Export report as PDF bytes.

        Uses a lightweight text-based PDF generator.
        No external dependencies required.
        """
        report = self.generate_executive_report(days)
        return self._generate_pdf(report)

    # ══════════════════════════════════════════════════════════
    # REPORT SECTIONS
    # ══════════════════════════════════════════════════════════

    def _build_executive_summary(self, days):
        """Build executive summary from dashboard data."""
        try:
            from app.services.dashboard_service import DashboardService
            ds = DashboardService()
            range_key = "today" if days <= 1 else ("7d" if days <= 7 else "30d")
            data = ds.get_dashboard_data(range_key)
            total = data.get("summary", {}).get("total", {})
            changes = data.get("comparison", {}).get("changes", {})

            return {
                "total_spend": round(total.get("spend", 0), 2),
                "total_conversions": total.get("conversions", 0),
                "avg_cpa": round(total.get("cpa", 0), 2),
                "avg_ctr": round(total.get("ctr", 0), 2),
                "spend_change_pct": changes.get("spend", 0),
                "conversion_change_pct": changes.get("conversions", 0),
                "period_days": days,
            }
        except Exception:
            return {"total_spend": 0, "total_conversions": 0, "avg_cpa": 0, "avg_ctr": 0, "period_days": days}

    def _get_growth_score(self, days):
        try:
            from app.services.growth_score_service import GrowthScoreService
            gs = GrowthScoreService()
            return gs.build_growth_score(days)
        except Exception:
            return {"score": 0, "label": "unknown", "summary": "Unable to compute growth score"}

    def _get_platform_comparison(self, days):
        try:
            from app.services.cross_platform_service import CrossPlatformService
            cp = CrossPlatformService()
            return cp.get_platform_summary(days)
        except Exception:
            return {"platforms": [], "total_spend": 0}

    def _get_top_campaigns(self, days):
        try:
            from app.services.snapshot_service import SnapshotService
            campaigns = SnapshotService.get_all_campaigns_latest()
            # Sort by conversions (desc), then by CPA (asc)
            converting = [c for c in campaigns if c.get("conversions", 0) > 0]
            converting.sort(key=lambda c: (-c.get("conversions", 0), c.get("cpa", float("inf"))))
            top = converting[:10]
            return {
                "campaigns": [{
                    "campaign_name": c.get("campaign_name", ""),
                    "platform": c.get("platform", ""),
                    "spend": round(c.get("spend", 0), 2),
                    "conversions": c.get("conversions", 0),
                    "cpa": round(c.get("cpa", 0), 2),
                    "ctr": round(c.get("ctr", 0), 2),
                    "status": c.get("status", ""),
                } for c in top],
                "total_campaigns": len(campaigns),
            }
        except Exception:
            return {"campaigns": [], "total_campaigns": 0}

    def _get_risks(self, days):
        try:
            from app.services.ai_coach_service import AICoachService
            coach = AICoachService()
            recs = coach.generate_recommendations(days)
            risks = [r for r in recs if r.get("severity") in ("critical", "warning")]
            return {
                "risks": risks[:5],
                "total_risks": len(risks),
            }
        except Exception:
            return {"risks": [], "total_risks": 0}

    def _get_opportunities(self, days):
        try:
            from app.services.ai_coach_service import AICoachService
            coach = AICoachService()
            recs = coach.generate_recommendations(days)
            opps = [r for r in recs if r.get("severity") == "success"]
            return {
                "opportunities": opps[:5],
                "total_opportunities": len(opps),
            }
        except Exception:
            return {"opportunities": [], "total_opportunities": 0}

    def _get_forecast_summary(self, days):
        try:
            from app.services.advanced_analytics_service import AdvancedAnalyticsService
            analytics = AdvancedAnalyticsService()
            return analytics.forecast_all_metrics(horizon_days=7)
        except Exception:
            return {"forecasts": {}}

    def _get_alert_summary(self):
        try:
            from app.db.init_db import get_connection
            conn = get_connection()
            try:
                critical = conn.execute(
                    "SELECT COUNT(*) as cnt FROM alerts WHERE resolved = 0 AND severity = 'critical'"
                ).fetchone()
                warning = conn.execute(
                    "SELECT COUNT(*) as cnt FROM alerts WHERE resolved = 0 AND severity = 'warning'"
                ).fetchone()
                total = conn.execute(
                    "SELECT COUNT(*) as cnt FROM alerts WHERE resolved = 0"
                ).fetchone()
                return {
                    "unresolved_total": total["cnt"] if total else 0,
                    "unresolved_critical": critical["cnt"] if critical else 0,
                    "unresolved_warnings": warning["cnt"] if warning else 0,
                }
            finally:
                conn.close()
        except Exception:
            return {"unresolved_total": 0, "unresolved_critical": 0, "unresolved_warnings": 0}

    # ══════════════════════════════════════════════════════════
    # PDF GENERATION (lightweight, no dependencies)
    # ══════════════════════════════════════════════════════════

    def _generate_pdf(self, report):
        """Generate a minimal PDF from report data.

        Uses raw PDF specification — no external library needed.
        Produces a simple text-based PDF document.
        """
        lines = []
        lines.append(report["title"])
        lines.append(f"Period: {report['period_days']} days | Generated: {report['generated_date']}")
        lines.append("")

        # Executive Summary
        summary = report["sections"].get("executive_summary", {})
        lines.append("EXECUTIVE SUMMARY")
        lines.append(f"  Total Spend: ${summary.get('total_spend', 0):.2f}")
        lines.append(f"  Total Conversions: {summary.get('total_conversions', 0)}")
        lines.append(f"  Average CPA: ${summary.get('avg_cpa', 0):.2f}")
        lines.append(f"  Average CTR: {summary.get('avg_ctr', 0):.2f}%")
        lines.append(f"  Spend Change: {summary.get('spend_change_pct', 0):+.1f}%")
        lines.append(f"  Conversion Change: {summary.get('conversion_change_pct', 0):+.1f}%")
        lines.append("")

        # Growth Score
        gs = report["sections"].get("growth_score", {})
        lines.append("GROWTH SCORE")
        lines.append(f"  Score: {gs.get('score', 0)}/100 ({gs.get('label', 'unknown')})")
        lines.append(f"  {gs.get('summary', '')}")
        lines.append("")

        # Platform Comparison
        pc = report["sections"].get("platform_comparison", {})
        platforms = pc.get("platforms", [])
        if platforms:
            lines.append("PLATFORM COMPARISON")
            for p in platforms:
                lines.append(f"  {p.get('platform', '').title()}: "
                             f"${p.get('spend', 0):.2f} spend | "
                             f"{p.get('conversions', 0)} conv | "
                             f"${p.get('avg_cpa', 0):.2f} CPA | "
                             f"{p.get('share_of_spend', 0):.1f}% share")
            lines.append("")

        # Top Campaigns
        tc = report["sections"].get("top_campaigns", {})
        campaigns = tc.get("campaigns", [])
        if campaigns:
            lines.append("TOP CAMPAIGNS")
            for c in campaigns[:5]:
                lines.append(f"  {c.get('campaign_name', '')}: "
                             f"{c.get('conversions', 0)} conv at "
                             f"${c.get('cpa', 0):.2f} CPA ({c.get('platform', '')})")
            lines.append("")

        # Risks
        risks = report["sections"].get("risks", {})
        risk_list = risks.get("risks", [])
        if risk_list:
            lines.append(f"RISKS ({risks.get('total_risks', 0)} total)")
            for r in risk_list[:3]:
                lines.append(f"  [{r.get('severity', '').upper()}] {r.get('title', '')}")
            lines.append("")

        # Opportunities
        opps = report["sections"].get("opportunities", {})
        opp_list = opps.get("opportunities", [])
        if opp_list:
            lines.append(f"OPPORTUNITIES ({opps.get('total_opportunities', 0)} total)")
            for o in opp_list[:3]:
                lines.append(f"  {o.get('title', '')}")
            lines.append("")

        # Forecasts
        fc = report["sections"].get("forecast", {})
        forecasts = fc.get("forecasts", {})
        if forecasts:
            lines.append("FORECAST (next 7 days)")
            for metric, data in forecasts.items():
                trend = data.get("trend_direction", "stable")
                conf = data.get("confidence", "low")
                current = data.get("current_value", 0)
                end = data.get("forecast_end_value", 0)
                lines.append(f"  {metric.upper()}: {current} -> {end} ({trend}, {conf} confidence)")
            lines.append("")

        # Alerts
        alerts = report["sections"].get("alert_summary", {})
        lines.append("ALERTS")
        lines.append(f"  Unresolved: {alerts.get('unresolved_total', 0)} "
                     f"({alerts.get('unresolved_critical', 0)} critical, "
                     f"{alerts.get('unresolved_warnings', 0)} warnings)")

        text_content = "\n".join(lines)
        return self._text_to_pdf(text_content, report["title"])

    @staticmethod
    def _text_to_pdf(text, title="Report"):
        """Convert plain text to a valid PDF document (no dependencies)."""
        # Escape special PDF characters
        # Replace non-latin-1 characters for PDF compatibility
        text = text.encode("latin-1", errors="replace").decode("latin-1")
        title = title.encode("latin-1", errors="replace").decode("latin-1")
        safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        safe_title = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        # Build PDF objects
        objects = []

        # Object 1: Catalog
        objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")

        # Object 2: Pages
        objects.append("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")

        # Object 3: Page
        objects.append("3 0 obj\n<< /Type /Page /Parent 2 0 R "
                       "/MediaBox [0 0 612 792] /Contents 4 0 R /Resources "
                       "<< /Font << /F1 5 0 R >> >> >>\nendobj")

        # Object 4: Content stream — render text line by line
        content_lines = []
        content_lines.append("BT")
        content_lines.append("/F1 10 Tf")
        y = 750
        for line in safe_text.split("\n"):
            if y < 40:
                break
            content_lines.append(f"1 0 0 1 40 {y} Tm")
            content_lines.append(f"({line}) Tj")
            y -= 14
        content_lines.append("ET")
        stream = "\n".join(content_lines)
        objects.append(f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj")

        # Object 5: Font
        objects.append("5 0 obj\n<< /Type /Font /Subtype /Type1 "
                       "/BaseFont /Courier >>\nendobj")

        # Build PDF
        pdf = "%PDF-1.4\n"
        offsets = []
        for obj in objects:
            offsets.append(len(pdf.encode("latin-1")))
            pdf += obj + "\n"

        xref_offset = len(pdf.encode("latin-1"))
        pdf += "xref\n"
        pdf += f"0 {len(objects) + 1}\n"
        pdf += "0000000000 65535 f \n"
        for offset in offsets:
            pdf += f"{offset:010d} 00000 n \n"

        pdf += "trailer\n"
        pdf += f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        pdf += "startxref\n"
        pdf += f"{xref_offset}\n"
        pdf += "%%EOF\n"

        return pdf.encode("latin-1")
