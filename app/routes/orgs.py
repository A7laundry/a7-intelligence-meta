"""Organization management routes."""
from flask import Blueprint, jsonify, request
from app.services.org_service import OrgService, DEFAULT_ORG_ID

orgs_bp = Blueprint("orgs", __name__)


@orgs_bp.route("/orgs/current")
def current_org():
    """Get current organization info."""
    return jsonify(OrgService.get_org(DEFAULT_ORG_ID))


@orgs_bp.route("/orgs/members")
def list_members():
    """List organization members."""
    return jsonify(OrgService.list_members(DEFAULT_ORG_ID))
