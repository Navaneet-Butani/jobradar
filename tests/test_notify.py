"""Chat alerts: allowlisted hosts only, platform-specific payloads, token never logged."""
import asyncio
import json

import httpx

from app.services.notify import format_message, send, webhook_kind


def test_only_allowlisted_https_hosts():
    assert webhook_kind("https://api.telegram.org/bot1:abc/sendMessage?chat_id=5") == "telegram"
    assert webhook_kind("https://discord.com/api/webhooks/1/x") == "discord"
    assert webhook_kind("https://hooks.slack.com/services/a/b/c") == "slack"
    assert webhook_kind("https://ntfy.sh/my-topic") == "ntfy"
    assert webhook_kind("http://discord.com/api/webhooks/1/x") is None      # not https
    assert webhook_kind("https://169.254.169.254/latest") is None          # internal address
    assert webhook_kind("https://discord.com.evil.example/x") is None
    assert webhook_kind(None) is None


def _post(url, text):
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = request.content
        return httpx.Response(200)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await send(url, text, client)
    return asyncio.run(go()), seen["body"]


def test_payload_per_platform():
    ok, body = _post("https://discord.com/api/webhooks/1/x", "x" * 3000)
    assert ok and len(json.loads(body)["content"]) == 2000
    ok, body = _post("https://api.telegram.org/bot1:abc/sendMessage?chat_id=5", "hi")
    assert json.loads(body)["text"] == "hi"
    ok, body = _post("https://ntfy.sh/topic", "hi")
    assert body == b"hi"


def test_message_lists_matches():
    text = format_message("Backend · Pune", [
        {"score": 82, "title": "Backend Engineer", "company": "Acme", "location": "Pune",
         "explanation": "Strong Python fit", "url": "http://localhost:3000/jobs/1"}])
    assert "1 new match for Backend · Pune" in text and "82 · Backend Engineer at Acme" in text
