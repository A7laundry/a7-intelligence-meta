"""Publishing Connector Service — provider-agnostic social publishing.

Provider selection:
  - If connector_ctx has access_token + platform-specific IDs → use real connector
  - Fallback: PUBLISHING_PROVIDER env var ('mock' default, 'manual' supported)

All providers return the same response schema:
  {
    "success":          bool,
    "external_post_id": str,
    "message":          str,
    "provider":         str,
    "credential_error": bool,   # True → do not retry
  }

HTTP layer (_http_post_form, _http_get) is overridable per-instance for testing.
"""

import hashlib
import os

_GRAPH_BASE = "https://graph.facebook.com"
_GRAPH_VER  = "v19.0"


class PublishingConnectorService:
    """Abstract publishing connector with real IG/FB + graceful mock fallback."""

    def __init__(self):
        self._fallback_provider = os.environ.get("PUBLISHING_PROVIDER", "mock").lower()

    # ── Public API ────────────────────────────────────────────────────────────

    def publish(self, platform_target, post_payload, connector_ctx=None):
        """Publish post to platform using real connector if credentials present.

        connector_ctx: dict with access_token, ig_user_id, page_id (from social_connectors row).
        Falls back to mock/manual if connector_ctx is None or lacks credentials.
        """
        if connector_ctx and connector_ctx.get("access_token"):
            if platform_target == "instagram" and connector_ctx.get("ig_user_id"):
                return self._publish_instagram(post_payload, connector_ctx)
            if platform_target == "facebook_page" and connector_ctx.get("page_id"):
                return self._publish_facebook_page(post_payload, connector_ctx)
            # Credentials exist but platform mismatch → warn + fallback
            return self._result_error(
                f"Connector configured for {connector_ctx.get('platform')} "
                f"but publishing to {platform_target}",
                credential_error=True,
                provider=platform_target,
            )

        # No credentials → fallback provider
        if self._fallback_provider == "manual":
            return self._publish_manual(platform_target, post_payload)
        return self._publish_mock(platform_target, post_payload)

    # ── Instagram ─────────────────────────────────────────────────────────────

    def _publish_instagram(self, post_payload, connector_ctx):
        """Publish image post to Instagram via Graph API (2-step)."""
        access_token = connector_ctx["access_token"]
        ig_user_id   = connector_ctx["ig_user_id"]
        image_url    = post_payload.get("asset_url", "")
        caption      = post_payload.get("caption", "")

        if not image_url:
            return self._result_error("No asset_url provided for Instagram publish",
                                      provider="instagram")

        # Step 1: Create media container
        try:
            container = self.upload_instagram_media(image_url, caption,
                                                    ig_user_id, access_token)
        except Exception as e:
            return self._classify_error(str(e), provider="instagram")

        creation_id = container.get("id") if isinstance(container, dict) else None
        if not creation_id:
            msg = (container.get("error", {}).get("message", "Container creation failed")
                   if isinstance(container, dict) else "Container creation failed")
            return self._classify_error(msg, provider="instagram")

        # Step 2: Publish container
        try:
            published = self.publish_instagram_container(creation_id, ig_user_id,
                                                         access_token)
        except Exception as e:
            return self._classify_error(str(e), provider="instagram")

        post_id = published.get("id") if isinstance(published, dict) else None
        if not post_id or "error" in (published or {}):
            msg = (published.get("error", {}).get("message", "Publish step failed")
                   if isinstance(published, dict) else "Publish step failed")
            return self._classify_error(msg, provider="instagram")

        return {
            "success": True,
            "external_post_id": str(post_id),
            "message": f"Published to Instagram (post_id={post_id})",
            "provider": "instagram",
            "credential_error": False,
        }

    def upload_instagram_media(self, image_url, caption, ig_user_id, access_token):
        """Step 1 — Create IG media container. Returns {id: ...} dict."""
        url = f"{_GRAPH_BASE}/{_GRAPH_VER}/{ig_user_id}/media"
        return self._http_post_form(url, {
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        })

    def publish_instagram_container(self, creation_id, ig_user_id, access_token):
        """Step 2 — Publish IG media container. Returns {id: ...} dict."""
        url = f"{_GRAPH_BASE}/{_GRAPH_VER}/{ig_user_id}/media_publish"
        return self._http_post_form(url, {
            "creation_id": creation_id,
            "access_token": access_token,
        })

    # ── Facebook Page ─────────────────────────────────────────────────────────

    def _publish_facebook_page(self, post_payload, connector_ctx):
        """Publish image post to Facebook Page via Graph API."""
        access_token = connector_ctx["access_token"]
        page_id      = connector_ctx["page_id"]
        image_url    = post_payload.get("asset_url", "")
        caption      = post_payload.get("caption", "")

        try:
            if image_url:
                result = self.upload_facebook_photo(image_url, caption,
                                                    page_id, access_token)
            else:
                result = self.publish_facebook_post(caption, page_id, access_token)
        except Exception as e:
            return self._classify_error(str(e), provider="facebook_page")

        post_id = result.get("post_id") or result.get("id") if isinstance(result, dict) else None
        if not post_id or "error" in (result or {}):
            msg = (result.get("error", {}).get("message", "FB publish failed")
                   if isinstance(result, dict) else "FB publish failed")
            return self._classify_error(msg, provider="facebook_page")

        return {
            "success": True,
            "external_post_id": str(post_id),
            "message": f"Published to Facebook Page (post_id={post_id})",
            "provider": "facebook_page",
            "credential_error": False,
        }

    def upload_facebook_photo(self, image_url, caption, page_id, access_token):
        """POST to /photos — returns {post_id, id} dict."""
        url = f"{_GRAPH_BASE}/{_GRAPH_VER}/{page_id}/photos"
        return self._http_post_form(url, {
            "url": image_url,
            "caption": caption,
            "access_token": access_token,
        })

    def publish_facebook_post(self, message, page_id, access_token):
        """POST to /feed — returns {id} dict."""
        url = f"{_GRAPH_BASE}/{_GRAPH_VER}/{page_id}/feed"
        return self._http_post_form(url, {
            "message": message,
            "access_token": access_token,
        })

    # ── Fallback Providers ────────────────────────────────────────────────────

    def _publish_mock(self, platform_target, post_payload):
        title  = post_payload.get("title", "untitled")
        seed   = f"{platform_target}:{title}"
        fake_id = "mock_" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
        return {
            "success": True,
            "external_post_id": fake_id,
            "message": f"[Mock] Post published to {platform_target}",
            "provider": "mock",
            "credential_error": False,
        }

    def _publish_manual(self, platform_target, post_payload):
        return {
            "success": True,
            "external_post_id": "",
            "message": (
                f"Manual publish required: copy the caption and upload the asset "
                f"directly to {platform_target}."
            ),
            "provider": "manual",
            "credential_error": False,
        }

    # ── HTTP layer (overridable for testing) ──────────────────────────────────

    def _http_post_form(self, url, data):
        """POST form-encoded via stdlib urllib — returns parsed JSON."""
        import json as _json
        import urllib.request
        import urllib.parse
        payload = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read())

    def _http_get(self, url, params=None):
        """GET via stdlib urllib — returns parsed JSON."""
        import json as _json
        import urllib.request
        import urllib.parse
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as resp:
            return _json.loads(resp.read())

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _result_error(message, provider="unknown", credential_error=False):
        return {
            "success": False,
            "external_post_id": "",
            "message": message,
            "provider": provider,
            "credential_error": credential_error,
        }

    @classmethod
    def _classify_error(cls, message, provider="unknown"):
        """Decide if error is a credential error (no retry) or transient (retry)."""
        cred_keywords = (
            "token", "permission", "oauth", "invalid_token", "auth",
            "access", "#190", "#102", "#200", "#10",
        )
        is_cred = any(kw in message.lower() for kw in cred_keywords)
        return cls._result_error(message, provider=provider,
                                 credential_error=is_cred)
