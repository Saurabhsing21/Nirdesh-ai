from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, tool

ToolRequestSender = Callable[[dict[str, Any]], Awaitable[None]]
ToolSpanObserver = Callable[[dict[str, Any]], Awaitable[None]]
TODO_TOOL_NAMES = frozenset({"todo_add", "todo_list", "todo_complete", "todo_delete"})
_tool_span_observer: ContextVar[ToolSpanObserver | None] = ContextVar(
    "tool_span_observer",
    default=None,
)


class ToolExecutionError(RuntimeError):
    pass


class ClientToolTimeoutError(ToolExecutionError):
    pass


@dataclass(frozen=True)
class SearchResult:
    title: str
    snippet: str
    url: str


class ExaSearchClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = http_client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = http_client is None

    async def search(self, query: str, *, max_results: int = 3) -> list[SearchResult]:
        normalized = " ".join(query.split())
        if not normalized:
            raise ToolExecutionError("Search query cannot be empty.")
        if self._api_key is None:
            raise ToolExecutionError(
                "Web search is unavailable because EXA_API_KEY is not configured."
            )
        response = await self._client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": self._api_key},
            json={
                "query": normalized,
                "type": "fast",
                "numResults": max_results,
                "contents": {
                    "highlights": {
                        "query": normalized,
                        "maxCharacters": 600,
                    }
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        raw_results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            raise ToolExecutionError("Exa returned a response without a results list.")
        results: list[SearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            title = item.get("title")
            highlights = item.get("highlights")
            snippet = (
                " ".join(
                    part.strip() for part in highlights if isinstance(part, str) and part.strip()
                )
                if isinstance(highlights, list)
                else ""
            )
            if not snippet:
                fallback = item.get("summary") or item.get("text")
                snippet = fallback.strip() if isinstance(fallback, str) else ""
            results.append(
                SearchResult(
                    title=title.strip() if isinstance(title, str) and title.strip() else url,
                    snippet=snippet[:900],
                    url=url,
                )
            )
        return results

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class ClientToolProxy:
    def __init__(self, *, sender: ToolRequestSender, timeout_seconds: float) -> None:
        self._sender = sender
        self._timeout_seconds = timeout_seconds
        self._pending: dict[str, asyncio.Future[Any]] = {}

    async def request(self, *, call_id: str, name: str, arguments: dict[str, Any]) -> Any:
        if name not in TODO_TOOL_NAMES:
            raise ToolExecutionError(f"Unsupported client tool: {name}")
        if call_id in self._pending:
            raise ToolExecutionError(f"Duplicate client tool call ID: {call_id}")
        future = asyncio.get_running_loop().create_future()
        self._pending[call_id] = future
        try:
            await self._sender(
                {
                    "type": "tool_request",
                    "call_id": call_id,
                    "name": name,
                    "arguments": arguments,
                }
            )
            try:
                return await asyncio.wait_for(future, timeout=self._timeout_seconds)
            except TimeoutError as exc:
                raise ClientToolTimeoutError(
                    f"The browser did not finish {name} within {self._timeout_seconds:g} seconds."
                ) from exc
        finally:
            self._pending.pop(call_id, None)

    def resolve(self, *, call_id: str, result: Any) -> bool:
        future = self._pending.get(call_id)
        if future is None or future.done():
            return False
        future.set_result(result)
        return True

    def cancel_pending(self) -> int:
        cancelled = 0
        for future in tuple(self._pending.values()):
            if not future.done():
                future.cancel()
                cancelled += 1
        return cancelled


def set_tool_span_observer(observer: ToolSpanObserver) -> Token[ToolSpanObserver | None]:
    return _tool_span_observer.set(observer)


def reset_tool_span_observer(token: Token[ToolSpanObserver | None]) -> None:
    _tool_span_observer.reset(token)


async def execute_measured(
    *,
    name: str,
    call_id: str,
    operation: Callable[[], Awaitable[Any]],
) -> str:
    started = time.monotonic()
    outcome = "success"
    error: str | None = None
    try:
        result = await operation()
        if isinstance(result, dict) and result.get("ok") is False:
            outcome = "error"
            reported_error = result.get("error")
            error = (
                reported_error
                if isinstance(reported_error, str)
                else "The client tool reported an error."
            )
    except asyncio.CancelledError:
        outcome = "cancelled"
        error = "Tool execution was cancelled because the voice turn was interrupted."
        raise
    except (ToolExecutionError, httpx.HTTPError) as exc:
        outcome = "error"
        error = str(exc)
        result = {"ok": False, "error": error}
    except Exception as exc:
        outcome = "error"
        error = f"{type(exc).__name__}: {exc}"
        result = {"ok": False, "error": "The tool failed unexpectedly."}
    finally:
        ended = time.monotonic()
        observer = _tool_span_observer.get()
        if observer is not None:
            await observer(
                {
                    "name": name,
                    "call_id": call_id,
                    "start_server": started,
                    "end_server": ended,
                    "duration_ms": (ended - started) * 1000,
                    "outcome": outcome,
                    "error": error,
                }
            )
    return json.dumps(result, ensure_ascii=False)


def build_agent_tools(
    *,
    exa_client: ExaSearchClient,
    todo_proxy: ClientToolProxy,
) -> list[BaseTool]:
    @tool
    async def web_search(query: str, runtime: ToolRuntime) -> str:
        """Search the live web for fresh or factual information."""

        call_id = runtime.tool_call_id or str(uuid.uuid4())

        async def operation() -> dict[str, Any]:
            results = await exa_client.search(query)
            return {"ok": True, "results": [asdict(result) for result in results]}

        return await execute_measured(
            name="web_search",
            call_id=call_id,
            operation=operation,
        )

    @tool
    async def todo_add(text: str, runtime: ToolRuntime) -> str:
        """Add a new item to the user's browser-local todo list."""

        call_id = runtime.tool_call_id or str(uuid.uuid4())
        return await execute_measured(
            name="todo_add",
            call_id=call_id,
            operation=lambda: todo_proxy.request(
                call_id=call_id,
                name="todo_add",
                arguments={"text": text},
            ),
        )

    @tool
    async def todo_list(runtime: ToolRuntime) -> str:
        """List all browser-local todos, including IDs and completion state."""

        call_id = runtime.tool_call_id or str(uuid.uuid4())
        return await execute_measured(
            name="todo_list",
            call_id=call_id,
            operation=lambda: todo_proxy.request(
                call_id=call_id,
                name="todo_list",
                arguments={},
            ),
        )

    @tool
    async def todo_complete(todo_id: str, runtime: ToolRuntime) -> str:
        """Mark one browser-local todo complete using its ID."""

        call_id = runtime.tool_call_id or str(uuid.uuid4())
        return await execute_measured(
            name="todo_complete",
            call_id=call_id,
            operation=lambda: todo_proxy.request(
                call_id=call_id,
                name="todo_complete",
                arguments={"todo_id": todo_id},
            ),
        )

    @tool
    async def todo_delete(todo_id: str, runtime: ToolRuntime) -> str:
        """Delete one browser-local todo using its ID."""

        call_id = runtime.tool_call_id or str(uuid.uuid4())
        return await execute_measured(
            name="todo_delete",
            call_id=call_id,
            operation=lambda: todo_proxy.request(
                call_id=call_id,
                name="todo_delete",
                arguments={"todo_id": todo_id},
            ),
        )

    return [web_search, todo_add, todo_list, todo_complete, todo_delete]
