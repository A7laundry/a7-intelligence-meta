"""Content Studio API routes."""

from flask import Blueprint, jsonify, request

content_bp = Blueprint("content", __name__)

_svc = None


def _get_svc():
    global _svc
    if _svc is None:
        from app.services.content_studio_service import ContentStudioService
        _svc = ContentStudioService()
    return _svc


def _account_id():
    return request.args.get("account_id") or (
        (request.get_json(silent=True) or {}).get("account_id")
    )


# ── Ideas ──────────────────────────────────────────────────────────────────


@content_bp.route("/content/ideas", methods=["GET"])
def list_ideas():
    """Return content ideas for an account."""
    acct = _account_id()
    status = request.args.get("status")
    try:
        return jsonify(_get_svc().list_ideas(account_id=acct, status=status))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/ideas", methods=["POST"])
def create_idea():
    """Create a new content idea."""
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    acct = body.get("account_id") or _account_id() or 1
    try:
        result = _get_svc().create_idea(
            account_id=acct,
            title=title,
            description=body.get("description", ""),
            content_type=body.get("content_type", "post"),
            platform_target=body.get("platform_target", "instagram"),
            status=body.get("status", "idea"),
            source=body.get("source", "manual"),
        )
        return jsonify(result), 201 if "id" in result else 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/generate-ideas", methods=["POST"])
def generate_ideas():
    """Generate content ideas from live marketing insights."""
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    try:
        ideas = _get_svc().generate_ideas(account_id=acct)
        return jsonify({"generated": len(ideas), "ideas": ideas})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Brand Kit ──────────────────────────────────────────────────────────────


@content_bp.route("/content/brand-kit", methods=["GET"])
def get_brand_kit():
    """Return brand kit for an account."""
    acct = _account_id() or 1
    try:
        return jsonify(_get_svc().get_brand_kit(account_id=acct))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/brand-kit", methods=["POST"])
def save_brand_kit():
    """Create or update brand kit for an account."""
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    try:
        return jsonify(_get_svc().save_brand_kit(account_id=acct, data=body))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Prompts ────────────────────────────────────────────────────────────────


@content_bp.route("/content/prompts", methods=["GET"])
def list_prompts():
    """Return creative prompts for an account."""
    acct = _account_id()
    try:
        return jsonify(_get_svc().list_prompts(account_id=acct))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/prompts", methods=["POST"])
def create_prompt():
    """Create a new creative prompt."""
    body = request.get_json(silent=True) or {}
    prompt_text = (body.get("prompt_text") or "").strip()
    if not prompt_text:
        return jsonify({"error": "prompt_text is required"}), 400
    acct = body.get("account_id") or _account_id() or 1
    try:
        result = _get_svc().create_prompt(
            account_id=acct,
            content_idea_id=body.get("content_idea_id"),
            prompt_text=prompt_text,
            style=body.get("style", "photorealistic"),
            aspect_ratio=body.get("aspect_ratio", "1:1"),
            image_type=body.get("image_type", "social_post"),
        )
        return jsonify(result), 201 if "id" in result else 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Assets ─────────────────────────────────────────────────────────────────


@content_bp.route("/content/assets", methods=["GET"])
def list_assets():
    """Return creative assets for an account."""
    acct = _account_id()
    status = request.args.get("status")
    try:
        return jsonify(_get_svc().list_assets(account_id=acct, status=status))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/ideas/<int:idea_id>/status", methods=["POST"])
def update_idea_status(idea_id):
    """Update the status (approve / reject) of a content idea."""
    body = request.get_json(silent=True) or {}
    status = (body.get("status") or "").strip()
    if not status:
        return jsonify({"error": "status is required"}), 400
    acct = body.get("account_id") or _account_id()
    try:
        result = _get_svc().update_idea_status(idea_id, status, account_id=acct)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/assets", methods=["POST"])
def create_asset():
    """Register a new creative asset."""
    body = request.get_json(silent=True) or {}
    acct = body.get("account_id") or _account_id() or 1
    try:
        result = _get_svc().create_asset(
            account_id=acct,
            content_idea_id=body.get("content_idea_id"),
            asset_type=body.get("asset_type", "image"),
            asset_url=body.get("asset_url", ""),
            thumbnail_url=body.get("thumbnail_url", ""),
            status=body.get("status", "draft"),
        )
        return jsonify(result), 201 if "id" in result else 422
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/assets/<int:asset_id>", methods=["GET"])
def get_asset(asset_id):
    """Return a single creative asset by id."""
    acct = _account_id()
    try:
        result = _get_svc().get_asset(asset_id, account_id=acct)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/prompts/build", methods=["POST"])
def build_prompt():
    """Build a structured prompt from brand kit + content idea."""
    body = request.get_json(silent=True) or {}
    content_idea_id = body.get("content_idea_id")
    if not content_idea_id:
        return jsonify({"error": "content_idea_id is required"}), 400
    acct = body.get("account_id") or _account_id() or 1
    try:
        result = _get_svc().build_prompt(
            account_id=acct,
            content_idea_id=content_idea_id,
            image_type=body.get("image_type", "social_post"),
        )
        if "error" in result:
            return jsonify(result), 422
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@content_bp.route("/content/assets/generate", methods=["POST"])
def generate_asset():
    """End-to-end pipeline: build prompt → generate image → save asset."""
    body = request.get_json(silent=True) or {}
    content_idea_id = body.get("content_idea_id")
    if not content_idea_id:
        return jsonify({"error": "content_idea_id is required"}), 400
    acct = body.get("account_id") or _account_id() or 1
    try:
        result = _get_svc().generate_asset_from_idea(
            account_id=acct,
            content_idea_id=content_idea_id,
            image_type=body.get("image_type", "social_post"),
        )
        if "error" in result:
            return jsonify(result), 422
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
