"""
Campaign Launch Console — API routes.

All routes require account_id.
Draft/validate mode is default and safe.
Live publish requires explicit mode=publish and dry_run=false.
"""

from flask import Blueprint, jsonify, request

from app.services.account_service import AccountService
from app.services.launch_service import LaunchService

launch_bp = Blueprint("launch", __name__)


def _acct() -> tuple:
    """Resolve account_id from request body or query string."""
    body = request.get_json(silent=True) or {}
    acc_id = body.get("account_id") or request.args.get("account_id")
    if acc_id:
        try:
            acc_id = int(acc_id)
        except (ValueError, TypeError):
            return None, jsonify({"error": "Invalid account_id"}), 400
    return acc_id, None, None


# ── Jobs ──────────────────────────────────────────────────────────────────

@launch_bp.route("/launch/jobs", methods=["GET"])
def list_jobs():
    account_id, err, code = _acct()
    if err:
        return err, code
    try:
        jobs = LaunchService.list_jobs(account_id=account_id)
        return jsonify({"jobs": jobs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/jobs", methods=["POST"])
def create_job():
    body = request.get_json(silent=True) or {}
    account_id = body.get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    try:
        account_id = int(account_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid account_id"}), 400

    job_name = body.get("job_name", "").strip()
    if not job_name:
        return jsonify({"error": "job_name required"}), 400

    mode = body.get("mode", "draft")
    if mode not in ("draft", "validate", "publish"):
        return jsonify({"error": "mode must be draft | validate | publish"}), 400

    try:
        job = LaunchService.create_job(
            account_id=account_id,
            job_name=job_name,
            mode=mode,
            template_id=body.get("template_id"),
            notes=body.get("notes", ""),
        )
        return jsonify({"job": job}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/jobs/<int:job_id>", methods=["GET"])
def get_job(job_id):
    try:
        job = LaunchService.get_job(job_id)
        if not job:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"job": job})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/jobs/<int:job_id>", methods=["DELETE"])
def delete_job(job_id):
    try:
        ok = LaunchService.delete_job(job_id)
        if not ok:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"status": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Items ─────────────────────────────────────────────────────────────────

@launch_bp.route("/launch/jobs/<int:job_id>/items", methods=["GET"])
def get_items(job_id):
    try:
        items = LaunchService.get_items(job_id)
        return jsonify({"items": items, "total": len(items)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/jobs/<int:job_id>/items", methods=["POST"])
def add_items(job_id):
    body = request.get_json(silent=True) or {}
    items = body.get("items", [])
    defaults = body.get("defaults", {})

    if not items:
        return jsonify({"error": "items array required"}), 400
    if len(items) > 100:
        return jsonify({"error": "Max 100 items per batch"}), 400

    try:
        ids = LaunchService.add_items(job_id, items, defaults)
        return jsonify({"added": len(ids), "item_ids": ids}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/jobs/<int:job_id>/import", methods=["POST"])
def import_csv(job_id):
    """Parse raw CSV/textarea input and add items."""
    body = request.get_json(silent=True) or {}
    raw = body.get("raw", "").strip()
    defaults = body.get("defaults", {})

    if not raw:
        return jsonify({"error": "raw input required"}), 400

    items, parse_errors = LaunchService.parse_csv_input(raw)
    if not items and parse_errors:
        return jsonify({"error": "Parse failed", "parse_errors": parse_errors}), 400

    # Apply naming patterns
    account_id = body.get("account_id")
    account_name = "A7"
    if account_id:
        try:
            acct = AccountService.get_by_id(int(account_id))
            if acct:
                account_name = acct.get("account_name", "A7")
        except Exception:
            pass

    template = None
    if body.get("template_id"):
        templates = LaunchService.list_templates(account_id or 0)
        for t in templates:
            if t["id"] == body["template_id"]:
                template = t
                break

    items = LaunchService.apply_naming_patterns(items, account_name, template)

    try:
        ids = LaunchService.add_items(job_id, items, defaults)
        return jsonify({
            "added": len(ids),
            "parse_errors": parse_errors,
            "item_ids": ids,
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Validate ──────────────────────────────────────────────────────────────

@launch_bp.route("/launch/jobs/<int:job_id>/validate", methods=["POST"])
def validate_job(job_id):
    try:
        summary = LaunchService.validate_job(job_id)
        items = LaunchService.get_items(job_id)
        return jsonify({"summary": summary, "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Publish ───────────────────────────────────────────────────────────────

@launch_bp.route("/launch/jobs/<int:job_id>/publish", methods=["POST"])
def publish_job(job_id):
    body = request.get_json(silent=True) or {}
    # Default to dry_run=True for safety
    dry_run = body.get("dry_run", True)

    # Extra safety: require explicit confirmation for live publish
    if not dry_run:
        confirm = body.get("confirm_live_publish", False)
        if not confirm:
            return jsonify({
                "error": "Live publish requires confirm_live_publish=true in request body",
                "hint": "Set dry_run=false AND confirm_live_publish=true to publish live"
            }), 400

    try:
        result = LaunchService.publish_job(job_id, dry_run=dry_run)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Logs ──────────────────────────────────────────────────────────────────

@launch_bp.route("/launch/jobs/<int:job_id>/logs", methods=["GET"])
def get_logs(job_id):
    try:
        logs = LaunchService.get_logs(job_id)
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Assets ────────────────────────────────────────────────────────────────

@launch_bp.route("/launch/assets", methods=["GET"])
def get_assets():
    account_id = request.args.get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    try:
        assets = LaunchService.discover_assets(int(account_id))
        return jsonify(assets)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/assets/save", methods=["POST"])
def save_assets():
    """Store page_id, pixel_id, instagram_actor_id on the account record."""
    body = request.get_json(silent=True) or {}
    account_id = body.get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400

    from app.db.init_db import get_connection
    conn = get_connection()
    try:
        updates = {}
        for field in ("page_id", "pixel_id", "instagram_actor_id", "bm_id", "currency", "timezone"):
            if field in body:
                updates[field] = body[field]
        if not updates:
            return jsonify({"error": "No fields to update"}), 400

        for field, value in updates.items():
            conn.execute(
                f"UPDATE ad_accounts SET {field}=? WHERE id=?",
                (value, int(account_id)),
            )
        conn.commit()
        return jsonify({"status": "saved", "updated": list(updates.keys())})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# ── Templates ─────────────────────────────────────────────────────────────

@launch_bp.route("/launch/templates", methods=["GET"])
def list_templates():
    account_id = request.args.get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    try:
        templates = LaunchService.list_templates(int(account_id))
        return jsonify({"templates": templates})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/templates", methods=["POST"])
def create_template():
    body = request.get_json(silent=True) or {}
    account_id = body.get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    try:
        template = LaunchService.create_template(int(account_id), body)
        return jsonify({"template": template}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Preview ───────────────────────────────────────────────────────────────

# ── Creative Library ──────────────────────────────────────────────────────

@launch_bp.route("/launch/creatives/upload", methods=["POST"])
def upload_creative():
    """
    Upload an image creative to Meta.
    Accepts multipart/form-data with fields:
      account_id (required)
      file (required — image file)
      creative_key (optional)
    Returns creative_library row including image_hash when successful.
    """
    account_id = request.form.get("account_id") or (request.get_json(silent=True) or {}).get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    try:
        account_id = int(account_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid account_id"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file field in request (use multipart/form-data with key 'file')"}), 400

    uploaded_file = request.files["file"]
    if not uploaded_file.filename:
        return jsonify({"error": "Empty filename"}), 400

    creative_key = request.form.get("creative_key", "").strip() or None

    try:
        file_bytes = uploaded_file.read()
        from app.services.creative_service_launch import CreativeLaunchService
        creative = CreativeLaunchService.upload_image(
            account_id=account_id,
            file_bytes=file_bytes,
            original_filename=uploaded_file.filename,
            creative_key=creative_key,
        )
        return jsonify({"creative": creative}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500


@launch_bp.route("/launch/creatives", methods=["GET"])
def list_creatives():
    account_id = request.args.get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    status = request.args.get("status")
    try:
        from app.services.creative_service_launch import CreativeLaunchService
        creatives = CreativeLaunchService.list_creatives(int(account_id), status=status)
        return jsonify({"creatives": creatives, "total": len(creatives)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/creatives/<int:creative_id>", methods=["GET"])
def get_creative(creative_id: int):
    try:
        from app.services.creative_service_launch import CreativeLaunchService
        creative = CreativeLaunchService.get_creative(creative_id)
        if not creative:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"creative": creative})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/creatives/<int:creative_id>/assign-key", methods=["POST"])
def assign_creative_key(creative_id: int):
    body = request.get_json(silent=True) or {}
    account_id = body.get("account_id")
    creative_key = (body.get("creative_key") or "").strip()
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    if not creative_key:
        return jsonify({"error": "creative_key required"}), 400
    try:
        from app.services.creative_service_launch import CreativeLaunchService
        updated = CreativeLaunchService.assign_key(creative_id, int(account_id), creative_key)
        if not updated:
            return jsonify({"error": "Not found or wrong account"}), 404
        return jsonify({"creative": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/creatives/<int:creative_id>", methods=["DELETE"])
def archive_creative(creative_id: int):
    account_id = request.args.get("account_id") or (request.get_json(silent=True) or {}).get("account_id")
    if not account_id:
        return jsonify({"error": "account_id required"}), 400
    try:
        from app.services.creative_service_launch import CreativeLaunchService
        ok = CreativeLaunchService.archive_creative(creative_id, int(account_id))
        if not ok:
            return jsonify({"error": "Not found or wrong account"}), 404
        return jsonify({"status": "archived"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@launch_bp.route("/launch/creatives/validate-key", methods=["GET"])
def validate_creative_key():
    account_id = request.args.get("account_id")
    creative_key = request.args.get("creative_key")
    if not account_id or not creative_key:
        return jsonify({"error": "account_id and creative_key required"}), 400
    try:
        from app.services.creative_service_launch import CreativeLaunchService
        result = CreativeLaunchService.validate_creative_key(int(account_id), creative_key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Preview ───────────────────────────────────────────────────────────────

@launch_bp.route("/launch/jobs/<int:job_id>/preview", methods=["GET"])
def preview_job(job_id):
    """Return full preview table: items with generated names and payloads."""
    try:
        items = LaunchService.get_items(job_id)
        job = LaunchService.get_job(job_id)
        if not job:
            return jsonify({"error": "Not found"}), 404

        # Build payload preview for each item
        account = AccountService.get_by_id(job["account_id"]) or {}

        previews = []
        for item in items:
            payload = LaunchService._build_meta_payload(item, account)
            previews.append({
                "id": item["id"],
                "row_index": item["row_index"],
                "lp_url": item["lp_url"],
                "campaign_name": payload["campaign"]["name"],
                "adset_name": payload["adset"]["name"],
                "ad_name": payload["ad"]["name"],
                "objective": payload["campaign"]["objective"],
                "budget": item.get("budget", 0),
                "cta": item.get("cta", "LEARN_MORE"),
                "creative_key": item.get("creative_key"),
                "validation_status": item.get("validation_status", "pending"),
                "validation_errors": item.get("validation_errors", []),
                "publish_status": item.get("publish_status", "pending"),
                "meta_campaign_id": item.get("meta_campaign_id"),
                "meta_adset_id": item.get("meta_adset_id"),
                "meta_ad_id": item.get("meta_ad_id"),
            })
        return jsonify({"job": job, "previews": previews})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
