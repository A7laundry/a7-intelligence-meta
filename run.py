"""A7 Intelligence — Application entry point."""

import argparse
import sys
import os

# Add project root to path for existing modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.db.init_db import init_db


def main():
    parser = argparse.ArgumentParser(description="A7 Intelligence Dashboard")
    parser.add_argument("--port", type=int, default=5050, help="Port to run on (default: 5050)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--init-db", action="store_true", help="Initialize database only")
    parser.add_argument("--snapshot", action="store_true", help="Take a snapshot and exit")
    args = parser.parse_args()

    if args.init_db:
        init_db()
        return

    if args.snapshot:
        init_db()
        from app.services.dashboard_service import DashboardService
        svc = DashboardService()
        data = svc.fetch_and_store("today")
        print(f"Snapshot stored. Spend: ${data['summary']['total']['spend']:.2f}")
        return

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
