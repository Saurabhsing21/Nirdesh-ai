from __future__ import annotations

import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain.agents import create_agent
from langchain.messages import AIMessage, AIMessageChunk, RemoveMessage
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from app.voice.tools import (
    ToolSpanObserver,
    reset_tool_span_observer,
    set_tool_span_observer,
)

ObservationCallback = Callable[[str, float, dict[str, Any]], Awaitable[None]]


class AgentObservabilityError(RuntimeError):
    pass


@dataclass
class AgentTimings:
    request_start: float | None = None
    first_visible: float | None = None
    complete: float | None = None


class _AgentTimingCallback(AsyncCallbackHandler):
    def __init__(self, timings: AgentTimings, observer: ObservationCallback) -> None:
        self._timings = timings
        self._observer = observer

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        del serialized, messages, kwargs
        if self._timings.request_start is None:
            self._timings.request_start = time.monotonic()
            await self._observer("t_llm_request_start", self._timings.request_start, {})


class AgentRunner:
    SYSTEM_PROMPT = (
        "You are Nirdesh AI, a concise voice assistant. Reply in the language used by the user. "
        "Use plain spoken text without markdown. Prefer one or two short sentences. "
        "Use web_search whenever a request depends on fresh, current, or externally verifiable "
        "facts. Ground the answer in its results, but never read URLs aloud. "
        "Use the todo tools for every request to add, list, complete, or delete a todo. "
        "Todo data belongs to the browser, so do not claim a todo action succeeded unless the "
        "tool result says it succeeded."
    )

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        thread_id: str,
        tools: list[BaseTool],
        system_prompt_extensions: Sequence[str] = (),
        chat_model: BaseChatModel | None = None,
        checkpointer: InMemorySaver | None = None,
    ) -> None:
        model = chat_model or ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            reasoning_effort=None,
            extra_body={"reasoning_effort": None},
            streaming=True,
            stream_usage=False,
            temperature=0.2,
            max_retries=1,
            timeout=60,
        )
        system_prompt = self.SYSTEM_PROMPT + "".join(system_prompt_extensions)
        self._agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=checkpointer or InMemorySaver(),
        )
        self._thread_id = thread_id

    def _config(self, callbacks: list[AsyncCallbackHandler] | None = None) -> dict[str, Any]:
        config: dict[str, Any] = {"configurable": {"thread_id": self._thread_id}}
        if callbacks:
            config["callbacks"] = callbacks
        return config

    async def stream_reply(
        self,
        transcript: str,
        *,
        observer: ObservationCallback,
        tool_observer: ToolSpanObserver,
    ) -> AsyncIterator[str]:
        timings = AgentTimings()
        callback = _AgentTimingCallback(timings, observer)
        config = self._config([callback])
        tool_observer_token = set_tool_span_observer(tool_observer)
        try:
            async for message, metadata in self._agent.astream(
                {"messages": [{"role": "user", "content": transcript}]},
                config=config,
                stream_mode="messages",
            ):
                if not isinstance(message, AIMessageChunk):
                    continue
                if metadata.get("langgraph_node") != "model":
                    continue
                text = message.text
                if not text:
                    continue
                if timings.request_start is None:
                    raise AgentObservabilityError(
                        "create_agent streamed visible text before "
                        "on_chat_model_start was observable"
                    )
                if timings.first_visible is None:
                    timings.first_visible = time.monotonic()
                    await observer("t_llm_first_visible_token", timings.first_visible, {})
                yield text

            if timings.request_start is None:
                raise AgentObservabilityError(
                    "create_agent did not expose the chat-model request-start callback"
                )
            timings.complete = time.monotonic()
            await observer("t_llm_complete", timings.complete, {})
        finally:
            reset_tool_span_observer(tool_observer_token)

    async def reconcile_interrupted_history(self, spoken_text: str) -> dict[str, Any]:
        config = self._config()
        snapshot = await self._agent.aget_state(config)
        messages = list(snapshot.values.get("messages", []))
        latest_user_index = max(
            (
                index
                for index, message in enumerate(messages)
                if getattr(message, "type", None) == "human"
            ),
            default=-1,
        )
        assistant_messages = [
            message
            for message in messages[latest_user_index + 1 :]
            if getattr(message, "type", None) == "ai" and getattr(message, "id", None)
        ]
        operations: list[Any] = [RemoveMessage(id=message.id) for message in assistant_messages]
        normalized_spoken = spoken_text.strip()
        if normalized_spoken:
            operations.append(AIMessage(content=normalized_spoken))
        if operations:
            await self._agent.aupdate_state(config, {"messages": operations})
        return {
            "removed_assistant_messages": len(assistant_messages),
            "retained_spoken_characters": len(normalized_spoken),
        }


def truncate_text_to_played_audio(
    text: str,
    *,
    played_audio_ms: float,
    generated_audio_ms: float,
) -> str:
    normalized = " ".join(text.split())
    if not normalized or played_audio_ms <= 0 or generated_audio_ms <= 0:
        return ""
    ratio = min(1.0, played_audio_ms / generated_audio_ms)
    if ratio >= 0.98:
        return normalized
    target_characters = max(0, math.floor(len(normalized) * ratio))
    prefix = normalized[:target_characters].rstrip()
    if target_characters < len(normalized) and not normalized[target_characters].isspace():
        prefix = prefix.rsplit(" ", 1)[0] if " " in prefix else ""
    return prefix.rstrip(" ,;:-")
