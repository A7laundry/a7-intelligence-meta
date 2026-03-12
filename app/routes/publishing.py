"""Publishing Engine API routes."""

from flask import Blueprint, jsonify, request

publishing_bp = Blueprint("publishing", __name__)

_svc = None
_conn_svc = None


def _get_svc():
    global _svc
    if _svc is None:
        from app.services.publishing_service import PublishingService
        _svc = PublishingService()
    return _svc


def _get_conn_svc():
    global _conn_svc
    if _conn_svc is None:
        from app.services.social_connector_service import SocialConnectorService
        _conn_svc = SocialConnectorService()
    return _conn_svc


def _account_id():
    return request.args.get("account_id") or (
        (request.get_json(silent=True) or {}).get("account_id")
    )


# ── Posts ───────────────────────────────────────────────────────────────────


@publishing_bp.route("/content/posts", methods=["GET"])
def list_posts():
    acct = _account_id()
    status = request.args.get("status")
    platform = request.args.get("platform_target")
    try:
        return jsonify(_get_svc().list_posts(account_id=acct, status=status,
                                             platform_target=platform))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/posts", methods=["POST"])
def create_post():
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    try:
        result = _get_svc().create_post(
            account_id=acct,
            content_idea_id=body.get("content_idea_id"),
            creative_asset_id=body.get("creative_asset_id"),
            title=body.get("title", ""),
            caption=body.get("caption", ""),
            platform_target=body.get("platform_target", "instagram"),
            post_type=body.get("post_type", "image_post"),
        )
        return jsonify(result), 201 if "id" in result else 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/posts/<int:post_id>", methods=["GET"])
def get_post(post_id):
    acct = _account_id()
    try:
        result = _get_svc().get_post(post_id, account_id=acct)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/posts/<int:post_id>/schedule", methods=["POST"])
def schedule_post(post_id):
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    scheduled_for = body.get("scheduled_for")
    if not scheduled_for:
        return jsonify({"error": "scheduled_for is required"}), 400
    try:
        result = _get_svc().schedule_post(post_id, account_id=acct,
                                          scheduled_for=scheduled_for)
        if "error" in result:
            return jsonify(result), 422
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/posts/<int:post_id>/publish", methods=["POST"])
def publish_post(post_id):
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    try:
        result = _get_svc().publish_post_now(post_id, account_id=acct)
        if "error" in result:
            return jsonify(result), 422
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/posts/<int:post_id>/status", methods=["POST"])
def update_post_status(post_id):
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    status = (body.get("status") or "").strip()
    if not status:
        return jsonify({"error": "status is required"}), 400
    try:
        result = _get_svc().update_post_status(post_id, account_id=acct, status=status)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Jobs ────────────────────────────────────────────────────────────────────


@publishing_bp.route("/content/jobs", methods=["GET"])
def list_jobs():
    acct = _account_id()
    status = request.args.get("status")
    try:
        return jsonify(_get_svc().list_jobs(account_id=acct, status=status))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/jobs/run-due", methods=["POST"])
def run_due_jobs():
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id()
    try:
        result = _get_svc().run_due_jobs(account_id=acct)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Social Connectors ────────────────────────────────────────────────────────


@publishing_bp.route("/content/connectors", methods=["GET"])
def list_connectors():
    acct = _account_id() or 1
    try:
        connectors = _get_conn_svc().list_connectors(account_id=acct)
        # Strip sensitive access_token from list response
        for c in connectors:
            if "access_token" in c:
                c["access_token"] = "***" if c["access_token"] else ""
        return jsonify(connectors)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/connectors", methods=["POST"])
def save_connector():
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    platform = body.get("platform")
    if not platform:
        return jsonify({"error": "platform is required"}), 400
    try:
        result = _get_conn_svc().save_connector(
            account_id=acct,
            platform=platform,
            access_token=body.get("access_token", ""),
            page_id=body.get("page_id", ""),
            ig_user_id=body.get("ig_user_id", ""),
        )
        if "error" in result:
            return jsonify(result), 422
        # Mask token in response
        if "access_token" in result:
            result["access_token"] = "***" if result["access_token"] else ""
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/connectors/validate", methods=["POST"])
def validate_connector():
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    platform = body.get("platform")
    if not platform:
        return jsonify({"error": "platform is required"}), 400
    try:
        result = _get_conn_svc().validate_connector(account_id=acct, platform=platform)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Webhook ──────────────────────────────────────────────────────────────────


@publishing_bp.route("/content/publish/webhook", methods=["POST"])
def publish_webhook():
    """Ingest provider webhook callbacks to update post/job status and metrics."""
    body = request.get_json(silent=True) or {}
    post_id = body.get("post_id") or body.get("content_post_id")
    if not post_id:
        return jsonify({"error": "post_id is required"}), 400
    try:
        result = _get_svc().ingest_webhook(
            post_id=int(post_id),
            external_post_id=body.get("external_post_id", ""),
            status=body.get("status", ""),
            metrics=body.get("metrics") or {},
        )
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Scheduler status ──────────────────────────────────────────────────────────


@publishing_bp.route("/content/scheduler/status", methods=["GET"])
def scheduler_status():
    """Return the current publishing scheduler status."""
    try:
        from app.services.scheduler_loop_service import get_scheduler_status
        return jsonify(get_scheduler_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@publishing_bp.route("/content/scheduler/run", methods=["POST"])
def scheduler_run_now():
    """Trigger a single scheduler pass immediately (for manual/testing use)."""
    try:
        from app.services.scheduler_loop_service import run_publishing_loop
        result = run_publishing_loop()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
