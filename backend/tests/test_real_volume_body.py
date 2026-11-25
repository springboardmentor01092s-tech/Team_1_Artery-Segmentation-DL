import asyncio
import json

from app.core import real_volume_body


def test_real_volume_middleware_rejects_oversized_stream_before_delivering_all_bytes(monkeypatch):
    monkeypatch.setattr(real_volume_body, "MAX_REAL_VOLUME_REQUEST_BYTES", 3)
    delivered = 0

    async def app(scope, receive, send):
        nonlocal delivered
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                break
            delivered += len(message.get("body", b""))
            if not message.get("more_body", False):
                break

    middleware = real_volume_body.RealVolumeResearchBodyLimit(
        app, path="/api/v1/experimental-stenosis/real-volume/analyze")
    messages = iter([
        {"type": "http.request", "body": b"ab", "more_body": True},
        {"type": "http.request", "body": b"cd", "more_body": False},
    ])
    sent = []
    async def receive(): return next(messages)
    async def send(message): sent.append(message)
    scope = {"type": "http", "method": "POST", "path": "/api/v1/experimental-stenosis/real-volume/analyze", "headers": []}
    asyncio.run(middleware(scope, receive, send))
    assert delivered == 2
    assert sent[0]["status"] == 413
    body = json.loads(sent[1]["body"])
    assert "request limit" in body["detail"]


def test_real_volume_middleware_rejects_declared_oversize_without_reading_body(monkeypatch):
    monkeypatch.setattr(real_volume_body, "MAX_REAL_VOLUME_REQUEST_BYTES", 3)
    async def app(scope, receive, send): raise AssertionError("endpoint must not execute")
    middleware = real_volume_body.RealVolumeResearchBodyLimit(
        app, path="/api/v1/experimental-stenosis/real-volume/analyze")
    sent = []
    async def receive(): raise AssertionError("oversized body must not be read")
    async def send(message): sent.append(message)
    scope = {"type": "http", "method": "POST", "path": "/api/v1/experimental-stenosis/real-volume/analyze",
             "headers": [(b"content-length", b"4")]}
    asyncio.run(middleware(scope, receive, send))
    assert sent[0]["status"] == 413
