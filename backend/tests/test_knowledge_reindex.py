from __future__ import annotations

from sqlalchemy import select

from app.knowledge.models import KnowledgeJobStatus, KnowledgeReindexJob
from app.knowledge.service import KnowledgeService
from app.models import User


class SwitchingEmbeddingClient:
    def __init__(self, *, fail_large: bool = False) -> None:
        self.fail_large = fail_large

    async def embed(self, texts, *, model_id: str, expected_dimensions: int):
        if self.fail_large and model_id == "text-embedding-3-large":
            raise RuntimeError("injected provider failure")
        return [[1.0] + [0.0] * (expected_dimensions - 1) for _ in texts]


class RecordingVectorStore:
    def __init__(self) -> None:
        self.points = []
        self.deleted_generations: list[str] = []

    async def upsert(self, *, collection: str, dimensions: int, points) -> None:
        del collection, dimensions
        self.points.extend(points)

    async def search(self, **kwargs):
        del kwargs
        return []

    async def delete_source(
        self,
        *,
        collection: str,
        user_id: str,
        source_id: str,
        generation_id: str,
    ) -> None:
        del collection, user_id, source_id
        self.deleted_generations.append(generation_id)


async def _user(database) -> User:
    async with database.session_factory() as session:
        user = User(email="switch@example.com", is_verified=True)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_reindex_switches_only_after_all_chunks_succeed(database, settings) -> None:
    configured = settings.model_copy(
        update={"knowledge_rag_enabled": True, "openai_api_key": "test-key"}
    )
    vectors = RecordingVectorStore()
    service = KnowledgeService(
        database=database,
        settings=configured,
        embedding_client=SwitchingEmbeddingClient(),
        vector_store=vectors,
    )
    user = await _user(database)
    old_profile = await service.save_profile(
        user_id=user.id,
        provider_id="openai",
        model_id="text-embedding-3-small",
    )
    await service.add_text_source(
        user_id=user.id,
        name="Policy",
        text="Refunds arrive after approval.",
    )

    pending = await service.save_profile(
        user_id=user.id,
        provider_id="openai",
        model_id="text-embedding-3-large",
    )
    assert pending.is_active is False
    assert pending.status.value == "pending"
    assert (await service.get_active_profile(user.id)).id == old_profile.id

    await service.run_pending_jobs()

    active = await service.get_active_profile(user.id)
    assert active.model_id == "text-embedding-3-large"
    assert active.generation_id == pending.generation_id
    assert old_profile.generation_id in vectors.deleted_generations
    async with database.session_factory() as session:
        job = (await session.execute(select(KnowledgeReindexJob))).scalar_one()
        assert job.status is KnowledgeJobStatus.COMPLETE
        assert job.processed_chunks == job.total_chunks == 1


async def test_failed_reindex_preserves_previous_active_profile(database, settings) -> None:
    configured = settings.model_copy(
        update={"knowledge_rag_enabled": True, "openai_api_key": "test-key"}
    )
    service = KnowledgeService(
        database=database,
        settings=configured,
        embedding_client=SwitchingEmbeddingClient(fail_large=True),
        vector_store=RecordingVectorStore(),
    )
    user = await _user(database)
    old_profile = await service.save_profile(
        user_id=user.id,
        provider_id="openai",
        model_id="text-embedding-3-small",
    )
    await service.add_text_source(user_id=user.id, name="Policy", text="Refund policy text.")
    await service.save_profile(
        user_id=user.id,
        provider_id="openai",
        model_id="text-embedding-3-large",
    )

    await service.run_pending_jobs()

    active = await service.get_active_profile(user.id)
    assert active.id == old_profile.id
    async with database.session_factory() as session:
        job = (await session.execute(select(KnowledgeReindexJob))).scalar_one()
        assert job.status is KnowledgeJobStatus.FAILED
        assert "provider failure" in (job.error_message or "")


async def test_new_service_instance_resumes_persisted_pending_job(database, settings) -> None:
    configured = settings.model_copy(
        update={"knowledge_rag_enabled": True, "openai_api_key": "test-key"}
    )
    vectors = RecordingVectorStore()
    first_service = KnowledgeService(
        database=database,
        settings=configured,
        embedding_client=SwitchingEmbeddingClient(),
        vector_store=vectors,
    )
    user = await _user(database)
    await first_service.save_profile(
        user_id=user.id,
        provider_id="openai",
        model_id="text-embedding-3-small",
    )
    await first_service.add_text_source(
        user_id=user.id,
        name="Policy",
        text="Persisted chunks can be rebuilt after restart.",
    )
    pending = await first_service.save_profile(
        user_id=user.id,
        provider_id="openai",
        model_id="text-embedding-3-large",
    )

    restarted_service = KnowledgeService(
        database=database,
        settings=configured,
        embedding_client=SwitchingEmbeddingClient(),
        vector_store=vectors,
    )
    await restarted_service.run_pending_jobs()

    active = await restarted_service.get_active_profile(user.id)
    assert active is not None
    assert active.id == pending.id
    job = await restarted_service.get_reindex_job(pending.id)
    assert job is not None
    assert job.status is KnowledgeJobStatus.COMPLETE
    assert job.processed_chunks == job.total_chunks == 1
