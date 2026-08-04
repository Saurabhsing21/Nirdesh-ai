from __future__ import annotations

import json
from types import SimpleNamespace

from app.knowledge.schemas import KnowledgeSearchResult
from app.knowledge.voice import KNOWLEDGE_SYSTEM_PROMPT, build_knowledge_voice_extension
from app.voice.tools import ClientToolProxy, ExaSearchClient, build_agent_tools


async def _sender(message) -> None:
    del message


def _base_dependencies():
    return {
        "exa_client": ExaSearchClient(api_key=None, timeout_seconds=1),
        "todo_proxy": ClientToolProxy(sender=_sender, timeout_seconds=1),
    }


async def test_knowledge_tool_is_absent_when_feature_is_disabled() -> None:
    dependencies = _base_dependencies()
    tools = build_agent_tools(**dependencies)
    assert "knowledge_search" not in {tool.name for tool in tools}
    await dependencies["exa_client"].close()


async def test_knowledge_tool_returns_structured_server_citations() -> None:
    class Service:
        async def search_knowledge(self, *, user_id: str, query: str, limit: int):
            assert user_id == "user-1"
            assert query == "refund timeline"
            assert limit == 4
            return [
                KnowledgeSearchResult(
                    chunk_id="chunk-1",
                    source_id="source-1",
                    source_name="Refund Policy",
                    excerpt="Approved refunds arrive within five working days.",
                    page_number=4,
                    score=0.91,
                )
            ]

    extension = build_knowledge_voice_extension(service=Service(), user_id="user-1")
    knowledge_tool = extension.tools[0]

    payload = json.loads(
        await knowledge_tool.coroutine(
            query="refund timeline",
            runtime=SimpleNamespace(tool_call_id="call-1"),
        )
    )

    assert payload["ok"] is True
    assert payload["results"][0]["citation"] == {
        "source_id": "source-1",
        "source_name": "Refund Policy",
        "page_number": 4,
    }
    assert payload["results"][0]["excerpt"].startswith("Approved refunds")


def test_voice_prompt_requires_grounded_spoken_citations() -> None:
    policy = KNOWLEDGE_SYSTEM_PROMPT.lower()
    assert "according to" in policy
    assert "never invent" in policy
    assert "no supporting result" in policy
