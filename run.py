"""A7 Intelligence — Application entry point.

Supports both web server mode and CLI operations for cron/scheduler use.

Usage:
  python run.py                        # Start web dashboard (port 5050)
  python run.py --init-db              # Initialize database only
  python run.py --snapshot             # Take a metrics snapshot
  python run.py --ai-refresh           # Refresh AI Coach + Creative + Budget
  python run.py --alerts-refresh       # Recompute alerts
  python run.py --daily-briefing       # Generate daily executive briefing
  python run.py --end-of-day           # Generate end-of-day summary
  python run.py --ops-status           # Show operations status
  python run.py --automation-evaluate  # Evaluate automation proposals (legacy)
  python run.py --automation-generate  # Generate and queue automation proposals
  python run.py --automation-run       # Execute approved automation actions
  python run.py --automation-status    # Show automation queue status
"""

import argparse
import json
import sys
import os

# Add project root to path for existing modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.db.init_db import init_db


def run_cli_operation(args):
    """Handle CLI operations (non-web-server commands)."""
    if args.init_db:
        init_db()
        return True

    if args.snapshot:
        from app.services.scheduler_service import SchedulerService
        result = SchedulerService().run_snapshot_job()
        print(f"[{'OK' if result['status'] == 'success' else 'FAIL'}] {result['message']}")
        return True

    if args.ai_refresh:
        from app.services.scheduler_service import SchedulerService
        result = SchedulerService().run_ai_refresh_job()
        print(f"[{'OK' if result['status'] == 'success' else 'FAIL'}] {result['message']}")
        return True

    if args.alerts_refresh:
        from app.services.scheduler_service import SchedulerService
        result = SchedulerService().run_alert_refresh_job()
        print(f"[{'OK' if result['status'] == 'success' else 'FAIL'}] {result['message']}")
        return True

    if args.daily_briefing:
        from app.services.scheduler_service import SchedulerService
        result = SchedulerService().run_daily_briefing_job()
        print(f"[{'OK' if result['status'] == 'success' else 'FAIL'}] {result['message']}")
        return True

    if args.end_of_day:
        from app.services.scheduler_service import SchedulerService
        result = SchedulerService().run_end_of_day_summary_job()
        print(f"[{'OK' if result['status'] == 'success' else 'FAIL'}] {result['message']}")
        return True

    if args.ops_status:
        from app.services.scheduler_service import SchedulerService
        status = SchedulerService().get_operations_status()
        print("Operations Status:")
        for op_type, info in status.items():
            s = info.get("status", "unknown")
            msg = info.get("message", "")
            ts = info.get("finished_at", "")
            print(f"  {op_type:20s} [{s:8s}] {msg[:60]} {ts}")
        return True

    if args.automation_evaluate:
        from app.services.automation_guardrails_service import AutomationGuardrailsService
        init_db()
        svc = AutomationGuardrailsService()
        proposals = svc.generate_proposals(days=7)
        result = svc.apply_guardrails(proposals)
        print(f"Automation Proposals: {result['total_proposals']} total, "
              f"{result['allowed_count']} allowed, {result['blocked_count']} blocked")
        print(f"Mode: {result['execution_mode']}")
        for p in result["allowed"]:
            print(f"  [ALLOW] {p['action_type']:20s} {p['entity_name']:30s} {p['reason'][:50]}")
        for p in result["blocked"]:
            print(f"  [BLOCK] {p['action_type']:20s} {p['entity_name']:30s} → {p['guardrail_reason']}")
        return True

    if args.automation_generate:
        from app.services.automation_engine import AutomationEngine
        init_db()
        engine = AutomationEngine()
        result = engine.generate_and_queue(days=7)
        print(f"Automation: {result['total_proposals']} proposals, "
              f"{result['queued_count']} queued, {result['blocked_count']} blocked")
        print(f"Mode: {result['execution_mode']}")
        for a in result["queued"]:
            print(f"  [QUEUED] #{a.get('id', '?'):4} {a['action_type']:20s} {a['entity_name']:30s}")
        for a in result["blocked"]:
            print(f"  [BLOCK]       {a['action_type']:20s} {a['entity_name']:30s} → {a.get('blocked_reason', '')}")
        return True

    if args.automation_run:
        from app.services.automation_engine import AutomationEngine
        init_db()
        engine = AutomationEngine()
        result = engine.execute_approved_actions()
        print(f"Automation Run: {result['executed_count']}/{result['total_approved']} executed "
              f"(max {result['max_per_run']} per run, mode: {result['execution_mode']})")
        for r in result["results"]:
            status = "OK" if r.get("success") else "FAIL"
            msg = r.get("message", r.get("error", ""))
            print(f"  [{status}] #{r.get('action_id', '?')} {msg[:70]}")
        return True

    if args.automation_status:
        from app.services.automation_engine import AutomationEngine
        init_db()
        engine = AutomationEngine()
        summary = engine.get_action_summary()
        config = engine.get_guardrails_config()
        print("Automation Status:")
        print(f"  Mode: {config['execution_mode']}")
        print(f"  Global Enabled: {config['global_enabled']}")
        print(f"  Total Actions: {summary.get('total', 0)}")
        for status in ("proposed", "approved", "executed", "rejected", "failed"):
            count = summary.get(status, 0)
            if count > 0:
                print(f"    {status:12s}: {count}")
        print(f"  Guardrails:")
        print(f"    Max actions/run: {config['max_actions_per_run']}")
        print(f"    Max budget change: {config['max_budget_change_pct']}%")
        print(f"    Min confidence: {config['min_confidence']}")
        print(f"    Cooldown: {config['cooldown_hours']}h")
        return True

    return False


def main():
    parser = argparse.ArgumentParser(description="A7 Intelligence Dashboard")
    parser.add_argument("--port", type=int, default=5050, help="Port to run on (default: 5050)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    # Database
    parser.add_argument("--init-db", action="store_true", help="Initialize database only")

    # Scheduled operations
    parser.add_argument("--snapshot", action="store_true", help="Take a metrics snapshot")
    parser.add_argument("--ai-refresh", action="store_true", help="Refresh AI Coach + Creative + Budget")
    parser.add_argument("--alerts-refresh", action="store_true", help="Recompute alerts")
    parser.add_argument("--daily-briefing", action="store_true", help="Generate daily executive briefing")
    parser.add_argument("--end-of-day", action="store_true", help="Generate end-of-day summary")
    parser.add_argument("--ops-status", action="store_true", help="Show operations status")

    # Automation
    parser.add_argument("--automation-evaluate", action="store_true", help="Evaluate automation proposals (legacy)")
    parser.add_argument("--automation-generate", action="store_true", help="Generate and queue automation proposals")
    parser.add_argument("--automation-run", action="store_true", help="Execute approved automation actions")
    parser.add_argument("--automation-status", action="store_true", help="Show automation queue status")

    args = parser.parse_args()

    # Check if any CLI operation was requested
    if run_cli_operation(args):
        return

    # Default: start web server
    app = create_app()

    print(f"""
    ╔══════════════════════════════════════╗
    ║     A7 Intelligence Dashboard v2     ║
    ║   http://{args.host}:{args.port}              ║
    ╚══════════════════════════════════════╝
    """)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
