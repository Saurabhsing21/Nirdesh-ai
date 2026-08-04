from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.voice.tools import (
    ClientToolProxy,
    ClientToolTimeoutError,
    ExaSearchClient,
    ToolExecutionError,
    execute_measured,
    reset_tool_span_observer,
    set_tool_span_observer,
)


async def test_client_tool_proxy_correlates_result() -> None:
    sent: list[dict[str, object]] = []

    async def sender(message: dict[str, object]) -> None:
        sent.append(message)

    proxy = ClientToolProxy(sender=sender, timeout_seconds=1)
    pending = asyncio.create_task(
        proxy.request(call_id="call-1", name="todo_add", arguments={"text": "buy milk"})
    )
    await asyncio.sleep(0)

    assert sent[0]["call_id"] == "call-1"
    assert proxy.resolve(call_id="call-1", result={"ok": True, "id": "todo-1"})
    assert await pending == {"ok": True, "id": "todo-1"}


async def test_client_tool_timeout_becomes_explicit_error() -> None:
    async def sender(message: dict[str, object]) -> None:
        del message

    proxy = ClientToolProxy(sender=sender, timeout_seconds=0.01)

    with pytest.raises(ClientToolTimeoutError, match="did not finish"):
        await proxy.request(call_id="call-1", name="todo_list", arguments={})


async def test_barge_in_cancels_pending_tool_and_discards_late_result() -> None:
    sent = asyncio.Event()

    async def sender(message: dict[str, object]) -> None:
        del message
        sent.set()

    proxy = ClientToolProxy(sender=sender, timeout_seconds=10)
    pending = asyncio.create_task(proxy.request(call_id="call-1", name="todo_list", arguments={}))
    await sent.wait()

    assert proxy.cancel_pending() == 1
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert not proxy.resolve(call_id="call-1", result={"ok": True})


async def test_exa_client_uses_mocked_httpx_and_normalizes_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "exa-key"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Fresh result",
                        "url": "https://example.test/result",
                        "highlights": [" First fact. ", "Second fact."],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ExaSearchClient(
            api_key="exa-key",
            timeout_seconds=1,
            http_client=http_client,
        )
        results = await client.search("  current   fact  ")

    assert results[0].title == "Fresh result"
    assert results[0].snippet == "First fact. Second fact."
    assert results[0].url == "https://example.test/result"


async def test_measured_tool_error_returns_model_visible_error_and_span() -> None:
    spans: list[dict[str, object]] = []

    async def observer(span: dict[str, object]) -> None:
        spans.append(span)

    async def operation() -> object:
        raise ToolExecutionError("tool is unavailable")

    token = set_tool_span_observer(observer)
    try:
        result = await execute_measured(
            name="web_search",
            call_id="call-1",
            operation=operation,
        )
    finally:
        reset_tool_span_observer(token)

    assert json.loads(result) == {"ok": False, "error": "tool is unavailable"}
    assert spans[0]["name"] == "web_search"
    assert spans[0]["outcome"] == "error"
    assert float(spans[0]["duration_ms"]) >= 0
