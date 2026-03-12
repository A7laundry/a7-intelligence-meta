"""Publishing Connector Service — provider-agnostic social publishing.

Provider resolution (via PUBLISHING_PROVIDER env var):
  1. mock    — deterministic fake publish (default, zero cost, always available)
  2. manual  — returns instructions for manual posting (no API calls)

Future connectors (not yet implemented):
  - instagram, facebook_page, google_business_profile, tiktok, linkedin, pinterest

All providers return the same response schema:
  {
    "success":          bool,
    "external_post_id": str,
    "message":          str,
    "provider":         str,
  }
"""

import os
import hashlib


class PublishingConnectorService:
    """Abstract publishing connector with graceful mock fallback."""

    SUPPORTED_PROVIDERS = ("mock", "manual")

    def __init__(self):
        self._provider = os.environ.get("PUBLISHING_PROVIDER", "mock").lower()
        if self._provider not in self.SUPPORTED_PROVIDERS:
            self._provider = "mock"

    # ── Public API ────────────────────────────────────────────────────────────

    def publish(self, platform_target, post_payload):
        """Publish a post payload to the given platform.

        Falls back to mock if real provider credentials are unavailable.
        """
        if self._provider == "manual":
            return self._publish_manual(platform_target, post_payload)
        return self._publish_mock(platform_target, post_payload)

    # ── Providers ─────────────────────────────────────────────────────────────

    def _publish_mock(self, platform_target, post_payload):
        """Simulate a successful publish — deterministic fake post id."""
        title = post_payload.get("title", "untitled")
        seed = f"{platform_target}:{title}"
        fake_id = "mock_" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
        return {
            "success": True,
            "external_post_id": fake_id,
            "message": f"[Mock] Post published to {platform_target}",
            "provider": "mock",
        }

    def _publish_manual(self, platform_target, post_payload):
        """Return manual posting instructions — no API call made."""
        return {
            "success": True,
            "external_post_id": "",
            "message": (
                f"Manual publish required: copy the caption and upload the asset "
                f"directly to {platform_target}."
            ),
            "provider": "manual",
        }
