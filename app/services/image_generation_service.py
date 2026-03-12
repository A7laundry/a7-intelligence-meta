"""Image Generation Service — provider-agnostic image creation with mock fallback.

Provider resolution order (via IMAGE_GENERATION_PROVIDER env var):
  1. openai   — DALL-E 3 via OpenAI API (requires OPENAI_API_KEY)
  2. mock     — deterministic placeholder (default, zero cost, always available)

All providers return the same response schema:
  {
    "asset_url":       str,
    "thumbnail_url":   str,
    "status":          "draft",
    "provider":        str,
    "generation_cost": float,
  }
"""

import os


# Aspect ratio → size mappings per provider
_OPENAI_SIZES = {
    "1:1":  "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "4:5":  "1024x1024",
}

# Placeholder dimensions for mock assets
_MOCK_DIMS = {
    "1:1":  "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "4:5":  "1024x1280",
}

# DALL-E 3 standard pricing (USD per image)
_DALLE3_COST = 0.04


class ImageGenerationService:
    """Generate images from text prompts via configurable providers."""

    def __init__(self):
        self._provider = os.environ.get("IMAGE_GENERATION_PROVIDER", "mock").lower()
        self._openai_key = os.environ.get("OPENAI_API_KEY", "")

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_image(self, prompt_text, image_type="social_post",
                       aspect_ratio="1:1", account_id=1):
        """Generate an image from a prompt and return asset metadata.

        Falls back to mock provider if the configured provider is unavailable.
        """
        if self._provider == "openai" and self._openai_key:
            result = self._generate_openai(prompt_text, aspect_ratio)
            if result:
                return result
        return self._generate_mock(prompt_text, image_type, aspect_ratio)

    # ── Providers ─────────────────────────────────────────────────────────────

    def _generate_openai(self, prompt_text, aspect_ratio):
        """Call DALL-E 3 via the openai SDK or raw HTTP."""
        size = _OPENAI_SIZES.get(aspect_ratio, "1024x1024")
        try:
            import openai
            client = openai.OpenAI(api_key=self._openai_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt_text[:4000],
                size=size,
                quality="standard",
                n=1,
            )
            url = response.data[0].url
            return {
                "asset_url": url,
                "thumbnail_url": url,
                "status": "draft",
                "provider": "openai_dalle3",
                "generation_cost": _DALLE3_COST,
            }
        except ImportError:
            return self._generate_openai_http(prompt_text, size)
        except Exception:
            return None  # signal caller to fall back to mock

    def _generate_openai_http(self, prompt_text, size):
        """DALL-E 3 via stdlib urllib — no SDK required."""
        import json as _json
        import urllib.request
        try:
            payload = _json.dumps({
                "model": "dall-e-3",
                "prompt": prompt_text[:4000],
                "size": size,
                "quality": "standard",
                "n": 1,
            }).encode()
            req = urllib.request.Request(
                "https://api.openai.com/v1/images/generations",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._openai_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = _json.loads(resp.read())
            url = body["data"][0]["url"]
            return {
                "asset_url": url,
                "thumbnail_url": url,
                "status": "draft",
                "provider": "openai_dalle3",
                "generation_cost": _DALLE3_COST,
            }
        except Exception:
            return None

    def _generate_mock(self, prompt_text, image_type, aspect_ratio):
        """Return a deterministic placeholder asset — always succeeds."""
        import hashlib
        prompt_hash = hashlib.md5(prompt_text.encode("utf-8", errors="replace")).hexdigest()[:8]
        dims = _MOCK_DIMS.get(aspect_ratio, "1024x1024")
        w, h = dims.split("x")
        label = image_type.replace("_", "+")
        base = f"https://placehold.co/{w}x{h}/3B82F6/ffffff"
        asset_url = f"{base}?text={label}"
        thumb_url = f"https://placehold.co/256x256/3B82F6/ffffff?text={label[:10]}"
        return {
            "asset_url": asset_url,
            "thumbnail_url": thumb_url,
            "status": "draft",
            "provider": "mock",
            "generation_cost": 0.0,
        }
