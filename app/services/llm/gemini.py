"""Shared Gemini Flash-Lite client — free-tier, JSON-safe, rate-limit-hardened.

Used by matching's LLM re-rank and by follow-up draft generation. Every
caller must degrade gracefully: if GEMINI_API_KEY is absent or a call
fails, return None and let the caller fall back to non-LLM behavior.
"""

import json
import logging
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ...config.settings import settings

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-flash-lite-latest:generateContent"
)
# Free-tier RPM is low enough that back-to-back calls reliably 429 even
# with retry — callers doing multiple calls in a loop should pace them.
SECONDS_BETWEEN_CALLS = 4.5


def is_enabled() -> bool:
    return bool(settings.gemini_api_key)


def _is_rate_limited(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception(_is_rate_limited),
    reraise=True,
)
async def _call(prompt: str, client: httpx.AsyncClient, max_output_tokens: int) -> httpx.Response:
    response = await client.post(
        GEMINI_URL,
        params={"key": settings.gemini_api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            # The "lite" tier doesn't do extended thinking (and rejects
            # thinkingConfig outright) — no reasoning budget wasted before
            # the actual answer.
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": max_output_tokens},
        },
        timeout=15.0,
    )
    response.raise_for_status()
    return response


def _extract_text(response: httpx.Response) -> str:
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


async def generate_text(prompt: str, client: httpx.AsyncClient, max_output_tokens: int = 300) -> Optional[str]:
    """Free-form text completion. Returns None on any failure."""
    if not is_enabled():
        return None
    try:
        response = await _call(prompt, client, max_output_tokens)
        return _extract_text(response)
    except Exception as e:
        logger.warning(f"Gemini text generation failed: {e}")
        return None


async def generate_json(prompt: str, client: httpx.AsyncClient, max_output_tokens: int = 200) -> Optional[dict]:
    """JSON-object completion — strips markdown code fences before parsing. Returns None on any failure."""
    if not is_enabled():
        return None
    try:
        response = await _call(prompt, client, max_output_tokens)
        text = _extract_text(response)
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Gemini JSON generation failed: {e}")
        return None
