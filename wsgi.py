"""WSGI entry point for Gunicorn (production deployment).

Usage:
  gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
"""

import os

# Load .env file when present (local dev / Railway env injection already sets vars)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
