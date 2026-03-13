"""Optional LLM adapter — OpenAI / Anthropic / disabled (graceful fallback)."""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_PROVIDER = os.environ.get("LLM_PROVIDER", "").lower()  # "openai" | "anthropic" | ""
_MODEL_OPENAI = os.environ.get("LLM_MODEL", "gpt-4o-mini")
_MODEL_ANTHROPIC = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")


def is_available() -> bool:
    return _PROVIDER in ("openai", "anthropic")


def complete(system_prompt: str, user_prompt: str, max_tokens: int = 300) -> Optional[str]:
    """Call LLM and return text, or None if unavailable/failed."""
    if not is_available():
        return None
    try:
        if _PROVIDER == "openai":
            return _call_openai(system_prompt, user_prompt, max_tokens)
        elif _PROVIDER == "anthropic":
            return _call_anthropic(system_prompt, user_prompt, max_tokens)
    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        return None


def _call_openai(system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None
    import requests
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": _MODEL_OPENAI,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.4,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    import requests
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": _MODEL_ANTHROPIC,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": max_tokens,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()
