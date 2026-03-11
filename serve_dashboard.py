#!/usr/bin/env python3
"""
A7 Laundry - Dashboard Server

Simple HTTP server for the dashboard. Serves files from the dashboard/ directory
and opens the browser automatically.

Usage:
    python3 serve_dashboard.py              # Serve on port 8050
    python3 serve_dashboard.py --port 9000  # Serve on custom port
    python3 serve_dashboard.py --no-open    # Don't open browser
"""

import argparse
import os
import sys
import webbrowser
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler


DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")


def serve(port=8050, open_browser=True):
    """Start an HTTP server serving the dashboard directory."""
    if not os.path.isdir(DASHBOARD_DIR):
        print(f"Error: Dashboard directory not found: {DASHBOARD_DIR}")
        print("Run 'python3 dashboard_fetcher.py --demo' first to generate data.")
        sys.exit(1)

    handler = partial(SimpleHTTPRequestHandler, directory=DASHBOARD_DIR)
    server = HTTPServer(("127.0.0.1", port), handler)

    url = f"http://127.0.0.1:{port}"
    print(f"Serving dashboard at {url}")
    print(f"  Directory: {DASHBOARD_DIR}")
    print(f"  Press Ctrl+C to stop\n")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="A7 Dashboard Server")
    parser.add_argument("--port", type=int, default=8050,
                        help="Port to serve on (default: 8050)")
    parser.add_argument("--no-open", action="store_true",
                        help="Don't open browser automatically")
    args = parser.parse_args()

    serve(port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()
