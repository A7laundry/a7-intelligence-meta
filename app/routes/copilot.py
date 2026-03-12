"""AI Marketing Copilot API routes."""

from flask import Blueprint, jsonify, request

from app.services.account_service import AccountService

copilot_bp = Blueprint("copilot", __name__)

_svc = None


def _get_service():
    global _svc
    if _svc is None:
        from app.services.copilot_service import CopilotService
        _svc = CopilotService()
    return _svc


@copilot_bp.route("/copilot/ask", methods=["POST"])
def ask():
    """Answer a natural language marketing question grounded in live data.

    Body (JSON):
        question        (str,  required)
        period          (str,  optional): today | 7d | 30d  — default 7d
        account_id      (int,  optional)
        session_context (list, optional): [{question, response_type, answer}, ...]
                        Last 2 entries used for conversation continuity.

    Returns:
        {response_type, answer, key_findings, suggested_actions,
         follow_up_questions, confidence, confidence_reason, sources,
         context_summary, provider, generated_at}
    """
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    period = body.get("period", "7d")
    account_id = AccountService.resolve_account_id(
        body.get("account_id") or request.args.get("account_id")
    )
    session_context = body.get("session_context") or []

    try:
        result = _get_service().ask(
            question,
            account_id=account_id,
            period=period,
            session_context=session_context,
        )
    except Exception as e:
        return jsonify({
            "response_type": "analysis",
            "answer": f"Copilot error: {str(e)}",
            "key_findings": [],
            "suggested_actions": [],
            "follow_up_questions": [],
            "confidence": "low",
            "confidence_reason": "Service error",
            "sources": [],
            "provider": "error",
        }), 500

    return jsonify(result)


@copilot_bp.route("/copilot/propose", methods=["POST"])
def propose():
    """Convert a Copilot suggested action into an Automation Engine proposal.

    The proposal is queued with status='proposed' and must be reviewed and
    approved in the Automation Center before any execution occurs.
    All guardrails apply — proposals that violate rules are blocked.

    Body (JSON):
        action_type          (str, required): pause_campaign | increase_budget |
                                              decrease_budget | refresh_creative | rotate_creative
        entity_name          (str, required): campaign or creative name
        entity_type          (str, optional): campaign | creative  — default campaign
        account_id           (int, optional)
        reason               (str, optional): rationale text from Copilot
        confidence           (str, optional): high | medium | low  — default medium
        platform             (str, optional): meta | google  — default meta
        campaign_id          (str, optional): Meta/Google campaign ID to store as entity_id
        suggested_change_pct (int, optional): Override default % change for budget actions

    Returns:
        {"success": true,  "action_id": int}  or
        {"success": false, "reason": str, "action_id": null}
    """
    body = request.get_json(silent=True) or {}
    action_type = (body.get("action_type") or "").strip()
    entity_name = (body.get("entity_name") or "").strip()

    if not action_type or not entity_name:
        return jsonify({"success": False,
                        "reason": "action_type and entity_name are required",
                        "action_id": None}), 400

    account_id = AccountService.resolve_account_id(
        body.get("account_id") or request.args.get("account_id")
    )

    try:
        result = _get_service().create_proposal(
            action_type=action_type,
            entity_name=entity_name,
            entity_type=body.get("entity_type", "campaign"),
            account_id=account_id,
            reason=body.get("reason", "Copilot suggestion"),
            confidence=body.get("confidence", "medium"),
            platform=body.get("platform", "meta"),
            campaign_id=body.get("campaign_id") or None,
            suggested_change_pct=body.get("suggested_change_pct"),
        )
    except Exception as e:
        return jsonify({"success": False, "reason": str(e), "action_id": None}), 500

    return jsonify(result)


@copilot_bp.route("/copilot/suggestions")
def suggestions():
    """Return example questions for suggestion chips.

    Includes the 4 primary navigation chips followed by deeper diagnostic questions.
    """
    return jsonify([
        "Investigate campaign performance",
        "Show budget opportunities",
        "Compare accounts",
        "Show automation activity",
        "Why did CPA increase in the last 7 days?",
        "Which campaigns should be scaled today?",
        "What are the biggest risks in my account?",
        "Which creatives are showing fatigue?",
    ])
