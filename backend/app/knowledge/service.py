from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from contextlib import suppress
from typing import Protocol

from sqlalchemy import delete, func, select, update

from app.config import Settings
from app.db import Database
from app.knowledge.embeddings import EmbeddingClientFactory
from app.knowledge.ingestion import ChunkDraft, ExtractedPage, chunk_pages
from app.knowledge.models import (
    EmbeddingProfile,
    EmbeddingProviderKey,
    KnowledgeChunk,
    KnowledgeJobStatus,
    KnowledgeProfileStatus,
    KnowledgeReindexJob,
    KnowledgeSource,
    KnowledgeSourceStatus,
)
from app.knowledge.providers import env_key_for, get_model_definition
from app.knowledge.schemas import KnowledgeSearchResult
from app.knowledge.vector_store import QdrantPoint
from app.models import new_id, utc_now


class UnknownEmbeddingProfileError(ValueError):
    pass


class EmbeddingProviderUnavailableError(RuntimeError):
    pass


class KnowledgeNotConfiguredError(RuntimeError):
    pass


class KnowledgeSourceLimitError(ValueError):
    pass


class KnowledgeSourceTooLargeError(ValueError):
    pass


class KnowledgeReindexInProgressError(RuntimeError):
    pass


class EmbeddingClient(Protocol):
    async def embed(
        self,
        texts: Sequence[str],
        *,
        model_id: str,
        expected_dimensions: int,
    ) -> list[list[float]]: ...


class VectorStore(Protocol):
    async def upsert(
        self, *, collection: str, dimensions: int, points: list[QdrantPoint]
    ) -> None: ...

    async def search(
        self,
        *,
        collection: str,
        vector: list[float],
        user_id: str,
        generation_id: str,
        limit: int,
    ) -> list[dict]: ...

    async def delete_source(
        self,
        *,
        collection: str,
        user_id: str,
        source_id: str,
        generation_id: str,
    ) -> None: ...


def collection_name(provider_id: str, model_id: str, dimensions: int) -> str:
    fingerprint = hashlib.sha256(
        f"{provider_id}:{model_id}:{dimensions}:cosine:chunker-v1".encode()
    ).hexdigest()[:24]
    return f"knowledge_{fingerprint}"


class KnowledgeService:
    def __init__(
        self,
        *,
        database: Database,
        settings: Settings,
        embedding_client: EmbeddingClient,
        vector_store: VectorStore | None = None,
        client_factory: EmbeddingClientFactory | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.embedding_client = embedding_client
        self.vector_store = vector_store
        self.client_factory = client_factory
        self._job_lock = asyncio.Lock()

    async def get_provider_key(self, user_id: str, provider_id: str) -> str | None:
        async with self.database.session_factory() as session:
            result = await session.execute(
                select(EmbeddingProviderKey.api_key).where(
                    EmbeddingProviderKey.user_id == user_id,
                    EmbeddingProviderKey.provider_id == provider_id,
                )
            )
            return result.scalar_one_or_none()

    async def set_provider_key(self, user_id: str, provider_id: str, api_key: str) -> None:
        async with self.database.session_factory() as session:
            existing = (
                await session.execute(
                    select(EmbeddingProviderKey).where(
                        EmbeddingProviderKey.user_id == user_id,
                        EmbeddingProviderKey.provider_id == provider_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    EmbeddingProviderKey(user_id=user_id, provider_id=provider_id, api_key=api_key)
                )
            else:
                existing.api_key = api_key
            await session.commit()

    async def delete_provider_key(self, user_id: str, provider_id: str) -> None:
        async with self.database.session_factory() as session:
            await session.execute(
                delete(EmbeddingProviderKey).where(
                    EmbeddingProviderKey.user_id == user_id,
                    EmbeddingProviderKey.provider_id == provider_id,
                )
            )
            await session.commit()

    async def provider_keys(self, user_id: str) -> dict[str, str]:
        async with self.database.session_factory() as session:
            rows = await session.execute(
                select(EmbeddingProviderKey.provider_id, EmbeddingProviderKey.api_key).where(
                    EmbeddingProviderKey.user_id == user_id
                )
            )
            return dict(rows.all())

    async def provider_available(self, user_id: str, provider_id: str) -> bool:
        if env_key_for(provider_id, self.settings) is not None:
            return True
        return await self.get_provider_key(user_id, provider_id) is not None

    async def _client_for(self, user_id: str, provider_id: str) -> EmbeddingClient:
        # Without a factory (unit tests inject a single fake client) the
        # configured client serves every provider.
        if self.client_factory is None:
            return self.embedding_client
        api_key = await self.get_provider_key(user_id, provider_id)
        if api_key is None:
            api_key = env_key_for(provider_id, self.settings)
        if api_key is None:
            raise EmbeddingProviderUnavailableError(
                "Add an API key for this embedding provider first"
            )
        return self.client_factory.client_for(provider_id, api_key)

    async def resolve_model(self, user_id: str, provider_id: str, model_id: str):
        model = get_model_definition(provider_id, model_id)
        if model is None:
            raise UnknownEmbeddingProfileError("Unsupported embedding provider or model")
        if not await self.provider_available(user_id, provider_id):
            raise EmbeddingProviderUnavailableError("Embedding provider is unavailable")
        return model

    async def test_profile(self, user_id: str, provider_id: str, model_id: str) -> int:
        model = await self.resolve_model(user_id, provider_id, model_id)
        client = await self._client_for(user_id, provider_id)
        vectors = await client.embed(
            ["NirdeshAI embedding connection test"],
            model_id=model.id,
            expected_dimensions=model.dimensions,
        )
        return len(vectors[0])

    async def get_active_profile(self, user_id: str) -> EmbeddingProfile | None:
        async with self.database.session_factory() as session:
            result = await session.execute(
                select(EmbeddingProfile)
                .where(
                    EmbeddingProfile.user_id == user_id,
                    EmbeddingProfile.is_active.is_(True),
                )
                .order_by(EmbeddingProfile.activated_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_latest_profile(self, user_id: str) -> EmbeddingProfile | None:
        async with self.database.session_factory() as session:
            result = await session.execute(
                select(EmbeddingProfile)
                .where(EmbeddingProfile.user_id == user_id)
                .order_by(EmbeddingProfile.created_at.desc(), EmbeddingProfile.id.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def get_reindex_job(self, profile_id: str) -> KnowledgeReindexJob | None:
        async with self.database.session_factory() as session:
            result = await session.execute(
                select(KnowledgeReindexJob)
                .where(KnowledgeReindexJob.profile_id == profile_id)
                .order_by(
                    KnowledgeReindexJob.created_at.desc(),
                    KnowledgeReindexJob.id.desc(),
                )
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def save_profile(
        self,
        *,
        user_id: str,
        provider_id: str,
        model_id: str,
    ) -> EmbeddingProfile:
        model = await self.resolve_model(user_id, provider_id, model_id)
        async with self.database.session_factory() as session:
            unfinished_job = (
                await session.execute(
                    select(KnowledgeReindexJob)
                    .where(
                        KnowledgeReindexJob.user_id == user_id,
                        KnowledgeReindexJob.status.in_(
                            [KnowledgeJobStatus.PENDING, KnowledgeJobStatus.RUNNING]
                        ),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if unfinished_job is not None:
                raise KnowledgeReindexInProgressError("A model reindex is already in progress")
            current = (
                await session.execute(
                    select(EmbeddingProfile)
                    .where(
                        EmbeddingProfile.user_id == user_id,
                        EmbeddingProfile.is_active.is_(True),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if (
                current is not None
                and current.provider_id == provider_id
                and current.model_id == model_id
            ):
                return current

            chunk_count = int(
                await session.scalar(
                    select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.user_id == user_id)
                )
                or 0
            )

            if current is not None and chunk_count > 0:
                profile = EmbeddingProfile(
                    user_id=user_id,
                    provider_id=provider_id,
                    model_id=model_id,
                    dimensions=model.dimensions,
                    generation_id=new_id(),
                    collection_name=collection_name(provider_id, model_id, model.dimensions),
                    status=KnowledgeProfileStatus.PENDING,
                    is_active=False,
                )
                session.add(profile)
                await session.flush()
                session.add(
                    KnowledgeReindexJob(
                        user_id=user_id,
                        profile_id=profile.id,
                        status=KnowledgeJobStatus.PENDING,
                        total_chunks=chunk_count,
                    )
                )
                await session.commit()
                await session.refresh(profile)
                return profile

            await session.execute(
                update(EmbeddingProfile)
                .where(
                    EmbeddingProfile.user_id == user_id,
                    EmbeddingProfile.is_active.is_(True),
                )
                .values(is_active=False)
            )
            profile = EmbeddingProfile(
                user_id=user_id,
                provider_id=provider_id,
                model_id=model_id,
                dimensions=model.dimensions,
                generation_id=new_id(),
                collection_name=collection_name(provider_id, model_id, model.dimensions),
                status=KnowledgeProfileStatus.READY,
                is_active=True,
                activated_at=utc_now(),
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            return profile

    async def run_pending_jobs(self) -> None:
        async with self._job_lock:
            await self._run_pending_jobs_locked()

    async def _run_pending_jobs_locked(self) -> None:
        async with self.database.session_factory() as session:
            job_ids = list(
                (
                    await session.execute(
                        select(KnowledgeReindexJob.id)
                        .where(
                            KnowledgeReindexJob.status.in_(
                                [KnowledgeJobStatus.PENDING, KnowledgeJobStatus.RUNNING]
                            )
                        )
                        .order_by(KnowledgeReindexJob.created_at)
                    )
                ).scalars()
            )
        for job_id in job_ids:
            await self._run_reindex_job(job_id)

    async def _run_reindex_job(self, job_id: str) -> None:
        if self.vector_store is None:
            return
        try:
            async with self.database.session_factory() as session:
                job = await session.get(KnowledgeReindexJob, job_id)
                if job is None or job.status not in {
                    KnowledgeJobStatus.PENDING,
                    KnowledgeJobStatus.RUNNING,
                }:
                    return
                profile = await session.get(EmbeddingProfile, job.profile_id)
                if profile is None:
                    return
                job.status = KnowledgeJobStatus.RUNNING
                chunks = list(
                    (
                        await session.execute(
                            select(KnowledgeChunk)
                            .where(KnowledgeChunk.user_id == job.user_id)
                            .order_by(KnowledgeChunk.source_id, KnowledgeChunk.ordinal)
                        )
                    ).scalars()
                )
                if len(chunks) != job.total_chunks:
                    raise RuntimeError("Knowledge changed during reindex; retry the model change")
                await session.commit()
                user_id = job.user_id
                processed = min(job.processed_chunks, len(chunks))

            reindex_client = await self._client_for(user_id, profile.provider_id)
            for start in range(
                processed,
                len(chunks),
                self.settings.knowledge_embedding_batch_size,
            ):
                batch = chunks[start : start + self.settings.knowledge_embedding_batch_size]
                vectors = await reindex_client.embed(
                    [chunk.content for chunk in batch],
                    model_id=profile.model_id,
                    expected_dimensions=profile.dimensions,
                )
                await self.vector_store.upsert(
                    collection=profile.collection_name,
                    dimensions=profile.dimensions,
                    points=[
                        QdrantPoint(
                            id=chunk.id,
                            vector=vector,
                            payload={
                                "user_id": user_id,
                                "source_id": chunk.source_id,
                                "chunk_id": chunk.id,
                                "generation_id": profile.generation_id,
                            },
                        )
                        for chunk, vector in zip(batch, vectors, strict=True)
                    ],
                )
                async with self.database.session_factory() as session:
                    await session.execute(
                        update(KnowledgeReindexJob)
                        .where(KnowledgeReindexJob.id == job_id)
                        .values(processed_chunks=start + len(batch))
                    )
                    await session.commit()

            async with self.database.session_factory() as session:
                old_profiles = list(
                    (
                        await session.execute(
                            select(EmbeddingProfile).where(
                                EmbeddingProfile.user_id == user_id,
                                EmbeddingProfile.is_active.is_(True),
                            )
                        )
                    ).scalars()
                )
                source_ids = list(
                    (
                        await session.execute(
                            select(KnowledgeSource.id).where(KnowledgeSource.user_id == user_id)
                        )
                    ).scalars()
                )
                await session.execute(
                    update(EmbeddingProfile)
                    .where(EmbeddingProfile.user_id == user_id)
                    .values(is_active=False)
                )
                await session.execute(
                    update(EmbeddingProfile)
                    .where(EmbeddingProfile.id == profile.id)
                    .values(
                        is_active=True,
                        status=KnowledgeProfileStatus.READY,
                        activated_at=utc_now(),
                        error_message=None,
                    )
                )
                await session.execute(
                    update(KnowledgeReindexJob)
                    .where(KnowledgeReindexJob.id == job_id)
                    .values(
                        status=KnowledgeJobStatus.COMPLETE,
                        processed_chunks=len(chunks),
                        error_message=None,
                    )
                )
                await session.commit()

            for old_profile in old_profiles:
                for source_id in source_ids:
                    with suppress(Exception):
                        await self.vector_store.delete_source(
                            collection=old_profile.collection_name,
                            user_id=user_id,
                            source_id=source_id,
                            generation_id=old_profile.generation_id,
                        )
        except Exception as exc:
            async with self.database.session_factory() as session:
                job = await session.get(KnowledgeReindexJob, job_id)
                if job is None:
                    return
                job.status = KnowledgeJobStatus.FAILED
                job.error_message = str(exc)
                profile = await session.get(EmbeddingProfile, job.profile_id)
                if profile is not None:
                    profile.status = KnowledgeProfileStatus.FAILED
                    profile.error_message = str(exc)
                await session.commit()

    async def add_text_source(
        self,
        *,
        user_id: str,
        name: str,
        text: str,
        media_type: str = "text/plain",
        pages: list[ExtractedPage] | None = None,
    ) -> KnowledgeSource:
        normalized_name = " ".join(name.split()).strip()
        normalized_text = text.strip()
        if not normalized_name or not normalized_text:
            raise ValueError("Source name and text are required")
        if len(normalized_text) > self.settings.knowledge_max_source_characters:
            raise KnowledgeSourceTooLargeError("Source text exceeds the configured limit")
        if self.vector_store is None:
            raise RuntimeError("Vector database is unavailable")
        profile = await self.get_active_profile(user_id)
        if profile is None:
            raise KnowledgeNotConfiguredError("Choose an embedding model before adding sources")
        await self._ensure_no_reindex(user_id)

        extracted_pages = pages or [ExtractedPage(normalized_text)]
        drafts = chunk_pages(
            extracted_pages,
            chunk_characters=self.settings.knowledge_chunk_characters,
            overlap=self.settings.knowledge_chunk_overlap,
        )
        if not drafts:
            raise ValueError("Source does not contain extractable text")
        source, chunks = await self._store_source_and_chunks(
            user_id=user_id,
            name=normalized_name,
            media_type=media_type,
            text=normalized_text,
            drafts=drafts,
        )
        try:
            source_client = await self._client_for(user_id, profile.provider_id)
            for start in range(0, len(chunks), self.settings.knowledge_embedding_batch_size):
                batch = chunks[start : start + self.settings.knowledge_embedding_batch_size]
                vectors = await source_client.embed(
                    [chunk.content for chunk in batch],
                    model_id=profile.model_id,
                    expected_dimensions=profile.dimensions,
                )
                await self.vector_store.upsert(
                    collection=profile.collection_name,
                    dimensions=profile.dimensions,
                    points=[
                        QdrantPoint(
                            id=chunk.id,
                            vector=vector,
                            payload={
                                "user_id": user_id,
                                "source_id": source.id,
                                "chunk_id": chunk.id,
                                "generation_id": profile.generation_id,
                            },
                        )
                        for chunk, vector in zip(batch, vectors, strict=True)
                    ],
                )
        except Exception as exc:
            await self._set_source_status(source.id, KnowledgeSourceStatus.FAILED, str(exc))
            raise
        await self._set_source_status(source.id, KnowledgeSourceStatus.INDEXED)
        source.status = KnowledgeSourceStatus.INDEXED
        return source

    async def _ensure_no_reindex(self, user_id: str) -> None:
        async with self.database.session_factory() as session:
            unfinished = await session.scalar(
                select(func.count(KnowledgeReindexJob.id)).where(
                    KnowledgeReindexJob.user_id == user_id,
                    KnowledgeReindexJob.status.in_(
                        [KnowledgeJobStatus.PENDING, KnowledgeJobStatus.RUNNING]
                    ),
                )
            )
        if int(unfinished or 0) > 0:
            raise KnowledgeReindexInProgressError(
                "New sources are paused while the embedding model is reindexing"
            )

    async def _store_source_and_chunks(
        self,
        *,
        user_id: str,
        name: str,
        media_type: str,
        text: str,
        drafts: list[ChunkDraft],
    ) -> tuple[KnowledgeSource, list[KnowledgeChunk]]:
        async with self.database.session_factory() as session:
            source_count = await session.scalar(
                select(func.count(KnowledgeSource.id)).where(KnowledgeSource.user_id == user_id)
            )
            if int(source_count or 0) >= self.settings.knowledge_max_sources_per_user:
                raise KnowledgeSourceLimitError("Knowledge source quota reached")
            source = KnowledgeSource(
                id=new_id(),
                user_id=user_id,
                name=name,
                media_type=media_type,
                content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                extracted_text=text,
                character_count=len(text),
                chunk_count=len(drafts),
                status=KnowledgeSourceStatus.PROCESSING,
            )
            chunks = [
                KnowledgeChunk(
                    id=new_id(),
                    source_id=source.id,
                    user_id=user_id,
                    ordinal=ordinal,
                    content=draft.content,
                    page_number=draft.page_number,
                )
                for ordinal, draft in enumerate(drafts)
            ]
            session.add(source)
            await session.flush()
            session.add_all(chunks)
            await session.commit()
            return source, chunks

    async def _set_source_status(
        self,
        source_id: str,
        status: KnowledgeSourceStatus,
        error_message: str | None = None,
    ) -> None:
        async with self.database.session_factory() as session:
            await session.execute(
                update(KnowledgeSource)
                .where(KnowledgeSource.id == source_id)
                .values(status=status, error_message=error_message)
            )
            await session.commit()

    async def list_sources(self, user_id: str) -> list[KnowledgeSource]:
        async with self.database.session_factory() as session:
            result = await session.execute(
                select(KnowledgeSource)
                .where(KnowledgeSource.user_id == user_id)
                .order_by(KnowledgeSource.created_at.desc())
            )
            return list(result.scalars())

    async def search_knowledge(
        self,
        *,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[KnowledgeSearchResult]:
        normalized_query = " ".join(query.split()).strip()
        if not normalized_query:
            raise ValueError("Search query is required")
        if len(normalized_query) > self.settings.knowledge_max_query_characters:
            raise KnowledgeSourceTooLargeError("Search query exceeds the configured limit")
        if self.vector_store is None:
            raise RuntimeError("Vector database is unavailable")
        profile = await self.get_active_profile(user_id)
        if profile is None:
            raise KnowledgeNotConfiguredError("Choose an embedding model before searching")
        search_client = await self._client_for(user_id, profile.provider_id)
        vector = (
            await search_client.embed(
                [normalized_query],
                model_id=profile.model_id,
                expected_dimensions=profile.dimensions,
            )
        )[0]
        hits = await self.vector_store.search(
            collection=profile.collection_name,
            vector=vector,
            user_id=user_id,
            generation_id=profile.generation_id,
            limit=limit,
        )
        chunk_ids = [str(hit.get("payload", {}).get("chunk_id", "")) for hit in hits]
        if not chunk_ids:
            return []
        async with self.database.session_factory() as session:
            rows = await session.execute(
                select(KnowledgeChunk, KnowledgeSource)
                .join(KnowledgeSource, KnowledgeSource.id == KnowledgeChunk.source_id)
                .where(
                    KnowledgeChunk.id.in_(chunk_ids),
                    KnowledgeChunk.user_id == user_id,
                    KnowledgeSource.user_id == user_id,
                    KnowledgeSource.status == KnowledgeSourceStatus.INDEXED,
                )
            )
            owned = {chunk.id: (chunk, source) for chunk, source in rows}
        results: list[KnowledgeSearchResult] = []
        for hit in hits:
            chunk_id = str(hit.get("payload", {}).get("chunk_id", ""))
            record = owned.get(chunk_id)
            if record is None:
                continue
            chunk, source = record
            results.append(
                KnowledgeSearchResult(
                    chunk_id=chunk.id,
                    source_id=source.id,
                    source_name=source.name,
                    excerpt=chunk.content,
                    page_number=chunk.page_number,
                    score=float(hit.get("score", 0.0)),
                )
            )
        return results

    async def delete_source(self, *, user_id: str, source_id: str) -> None:
        async with self.database.session_factory() as session:
            source = (
                await session.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.id == source_id,
                        KnowledgeSource.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if source is None:
                return
            profiles = list(
                (
                    await session.execute(
                        select(EmbeddingProfile).where(EmbeddingProfile.user_id == user_id)
                    )
                ).scalars()
            )
            await session.delete(source)
            await session.commit()
        if self.vector_store is None:
            return
        for profile in profiles:
            await self.vector_store.delete_source(
                collection=profile.collection_name,
                user_id=user_id,
                source_id=source_id,
                generation_id=profile.generation_id,
            )
