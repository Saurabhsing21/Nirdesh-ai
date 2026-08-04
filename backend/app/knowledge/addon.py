from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI

from app.config import Settings
from app.db import Database
from app.knowledge import models as _models  # noqa: F401 - register add-on tables
from app.knowledge.embeddings import EmbeddingClientFactory, OpenAIEmbeddingClient
from app.knowledge.router import router
from app.knowledge.service import KnowledgeService
from app.knowledge.vector_store import QdrantVectorStore
from app.knowledge.voice import build_knowledge_voice_extension
from app.voice.extensions import VoiceAgentExtension


class KnowledgeAddon:
    router = router

    def __init__(self, *, settings: Settings, database: Database) -> None:
        self._settings = settings
        self._database = database
        self._service: KnowledgeService | None = None

    @asynccontextmanager
    async def lifespan(
        self,
        app: FastAPI,
        http_client: httpx.AsyncClient,
    ) -> AsyncIterator[None]:
        service = KnowledgeService(
            database=self._database,
            settings=self._settings,
            embedding_client=OpenAIEmbeddingClient(
                api_key=self._settings.openai_api_key_value,
                http_client=http_client,
            ),
            vector_store=QdrantVectorStore(
                base_url=self._settings.qdrant_url,
                http_client=http_client,
            ),
            client_factory=EmbeddingClientFactory(http_client=http_client),
        )
        self._service = service
        app.state.knowledge_service = service
        resume_task = asyncio.create_task(service.run_pending_jobs())
        try:
            yield
        finally:
            if not resume_task.done():
                resume_task.cancel()
            with suppress(asyncio.CancelledError):
                await resume_task
            self._service = None
            del app.state.knowledge_service

    def voice_extension_factory(self, user_id: str) -> VoiceAgentExtension:
        if self._service is None:
            raise RuntimeError("Knowledge add-on has not started")
        return build_knowledge_voice_extension(service=self._service, user_id=user_id)
