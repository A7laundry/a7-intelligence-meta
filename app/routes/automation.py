"""Automation Engine API routes."""

from flask import Blueprint, jsonify, request

from app.services.automation_engine import AutomationEngine

automation_bp = Blueprint("automation", __name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = AutomationEngine()
    return _engine


# ── Actions ──────────────────────────────────────────────────

@automation_bp.route("/automation/actions")
def list_actions():
    """List all automation actions, optionally filtered by status/platform."""
    status = request.args.get("status")
    platform = request.args.get("platform")
    limit = request.args.get("limit", 50, type=int)
    try:
        actions = _get_engine().get_actions(status=status, platform=platform, limit=limit)
        summary = _get_engine().get_action_summary()
    except Exception as e:
        return jsonify({"actions": [], "error": str(e)})
    return jsonify({"actions": actions, "summary": summary})


@automation_bp.route("/automation/pending")
def pending_actions():
    """List pending (proposed) actions awaiting approval."""
    try:
        actions = _get_engine().get_pending_actions()
    except Exception as e:
        return jsonify({"actions": [], "error": str(e)})
    return jsonify({"actions": actions, "count": len(actions)})


# ── Generate ─────────────────────────────────────────────────

@automation_bp.route("/automation/generate", methods=["POST"])
def generate_proposals():
    """Generate new automation proposals and queue them."""
    days = request.args.get("days", 7, type=int)
    platform = request.args.get("platform")
    try:
        result = _get_engine().generate_and_queue(days=days, platform=platform)
    except Exception as e:
        result = {"queued": [], "blocked": [], "error": str(e)}
    return jsonify(result)


# ── Approve / Reject / Execute ───────────────────────────────

@automation_bp.route("/automation/<int:action_id>/approve", methods=["POST"])
def approve_action(action_id):
    """Approve a proposed action."""
    try:
        result = _get_engine().approve_action(action_id)
    except Exception as e:
        result = {"success": False, "error": str(e)}
    return jsonify(result)


@automation_bp.route("/automation/<int:action_id>/reject", methods=["POST"])
def reject_action(action_id):
    """Reject a proposed action."""
    try:
        result = _get_engine().reject_action(action_id)
    except Exception as e:
        result = {"success": False, "error": str(e)}
    return jsonify(result)


@automation_bp.route("/automation/<int:action_id>/execute", methods=["POST"])
def execute_action(action_id):
    """Execute an approved action."""
    try:
        result = _get_engine().execute_action(action_id)
    except Exception as e:
        result = {"success": False, "error": str(e)}
    return jsonify(result)


# ── Logs ─────────────────────────────────────────────────────

@automation_bp.route("/automation/logs")
def automation_logs():
    """Get automation execution logs."""
    action_id = request.args.get("action_id", type=int)
    limit = request.args.get("limit", 50, type=int)
    try:
        logs = _get_engine().get_logs(action_id=action_id, limit=limit)
    except Exception as e:
        return jsonify({"logs": [], "error": str(e)})
    return jsonify({"logs": logs, "count": len(logs)})
