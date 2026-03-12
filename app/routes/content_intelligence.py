"""Content Intelligence API routes — Phase 8F."""

from flask import Blueprint, jsonify, request

content_intelligence_bp = Blueprint("content_intelligence", __name__)

_svc = None


def _get_svc():
    global _svc
    if _svc is None:
        from app.services.content_intelligence_service import ContentIntelligenceService
        _svc = ContentIntelligenceService()
    return _svc


def _acct():
    return int(
        request.args.get("account_id")
        or (request.get_json(silent=True) or {}).get("account_id")
        or 1
    )


def _days(default=7):
    try:
        return max(1, min(365, int(request.args.get("days", default))))
    except (ValueError, TypeError):
        return default


# ── Sync ─────────────────────────────────────────────────────────────────────


@content_intelligence_bp.route("/content/intelligence/sync", methods=["POST"])
def sync_metrics():
    body = request.get_json(silent=True) or {}
    acct = int(body.get("account_id") or 1)
    try:
        result = _get_svc().sync_content_metrics(account_id=acct)
        if "error" in result:
            return jsonify(result), 500
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Summary ───────────────────────────────────────────────────────────────────


@content_intelligence_bp.route("/content/intelligence/summary", methods=["GET"])
def get_summary():
    try:
        return jsonify(_get_svc().get_content_summary(account_id=_acct(), days=_days(7)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Top Posts ─────────────────────────────────────────────────────────────────


@content_intelligence_bp.route("/content/intelligence/top-posts", methods=["GET"])
def get_top_posts():
    try:
        return jsonify(_get_svc().get_top_posts(account_id=_acct(), days=_days(7)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Format Performance ────────────────────────────────────────────────────────


@content_intelligence_bp.route("/content/intelligence/formats", methods=["GET"])
def get_formats():
    try:
        return jsonify(_get_svc().get_format_performance(account_id=_acct(), days=_days(30)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Best Times ────────────────────────────────────────────────────────────────


@content_intelligence_bp.route("/content/intelligence/best-times", methods=["GET"])
def get_best_times():
    try:
        return jsonify(_get_svc().get_best_posting_times(account_id=_acct(), days=_days(30)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Reuse Opportunities ───────────────────────────────────────────────────────


@content_intelligence_bp.route("/content/intelligence/reuse", methods=["GET"])
def get_reuse():
    try:
        return jsonify(_get_svc().detect_reuse_opportunities(account_id=_acct(), days=_days(30)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
