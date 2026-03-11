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
        question  (str, required)
        period    (str, optional): today | 7d | 30d  (default: 7d)
        account_id (int, optional)

    Returns:
        {answer, key_findings, suggested_actions, confidence, sources,
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

    try:
        result = _get_service().ask(question, account_id=account_id, period=period)
    except Exception as e:
        return jsonify({
            "answer": f"Copilot error: {str(e)}",
            "key_findings": [],
            "suggested_actions": [],
            "confidence": "low",
            "sources": [],
            "provider": "error",
        }), 500

    return jsonify(result)


@copilot_bp.route("/copilot/suggestions")
def suggestions():
    """Return example questions for the Copilot UI."""
    return jsonify([
        "Why did CPA increase in the last 7 days?",
        "Which campaigns should be scaled today?",
        "Where should budget be moved right now?",
        "What are the biggest risks in my account?",
        "Which creatives are showing fatigue?",
        "How did performance change vs. last week?",
        "Which account has the highest growth potential?",
    ])
