"""The LLM client talks to Gemini or any OpenAI-compatible API; both parse the same."""
import asyncio
import json

import httpx

from app.config.settings import settings
from app.services.llm import gemini


def _run(handler, **overrides):
    saved = {k: getattr(settings, k) for k in overrides}
    for k, v in overrides.items():
        setattr(settings, k, v)
    try:
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await gemini.generate_json("say hi as json", client)
        return asyncio.run(go())
    finally:
        for k, v in saved.items():
            setattr(settings, k, v)


def test_openai_compatible_backend():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]})

    out = _run(handler, llm_base_url="http://localhost:11434/v1/", llm_model="", gemini_api_key=None)
    assert out == {"ok": True}
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["body"]["model"] == "llama3.1"  # empty LLM_MODEL falls back


def test_gemini_backend():
    def handler(request: httpx.Request):
        assert "generativelanguage.googleapis.com" in str(request.url)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"ok": 1}'}]}}]})

    assert _run(handler, llm_base_url=None, gemini_api_key="test") == {"ok": 1}


def test_disabled_returns_none():
    assert _run(lambda r: httpx.Response(500), llm_base_url=None, gemini_api_key=None) is None
