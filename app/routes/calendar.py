"""Content Calendar API routes."""

from flask import Blueprint, jsonify, request

calendar_bp = Blueprint("calendar", __name__)

_svc = None


def _get_svc():
    global _svc
    if _svc is None:
        from app.services.calendar_service import CalendarService
        _svc = CalendarService()
    return _svc


def _account_id():
    return request.args.get("account_id") or (
        (request.get_json(silent=True) or {}).get("account_id")
    )


# ── Calendar view ────────────────────────────────────────────────────────────


@calendar_bp.route("/content/calendar", methods=["GET"])
def get_calendar():
    acct = _account_id() or 1
    view = request.args.get("view", "week")
    start = request.args.get("start")
    if view not in ("day", "week", "month"):
        return jsonify({"error": "view must be day, week, or month"}), 400
    try:
        return jsonify(_get_svc().get_calendar(account_id=acct, view=view, start=start))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Reschedule ───────────────────────────────────────────────────────────────


@calendar_bp.route("/content/calendar/reschedule", methods=["POST"])
def reschedule_post():
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    post_id = body.get("post_id")
    scheduled_for = body.get("scheduled_for")
    if not post_id:
        return jsonify({"error": "post_id is required"}), 400
    if not scheduled_for:
        return jsonify({"error": "scheduled_for is required"}), 400
    try:
        result = _get_svc().reschedule_post(
            account_id=acct, post_id=post_id, scheduled_for=scheduled_for
        )
        if "error" in result:
            return jsonify(result), 422
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Upcoming queue ───────────────────────────────────────────────────────────


@calendar_bp.route("/content/calendar/upcoming", methods=["GET"])
def get_upcoming():
    acct = _account_id() or 1
    limit = min(int(request.args.get("limit", 20)), 100)
    try:
        return jsonify(_get_svc().get_upcoming(account_id=acct, limit=limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
