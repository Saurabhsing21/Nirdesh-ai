from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class EmbeddingModelDefinition:
    id: str
    label: str
    dimensions: int
    default: bool = False


@dataclass(frozen=True)
class EmbeddingProviderDefinition:
    id: str
    label: str
    models: tuple[EmbeddingModelDefinition, ...]


OPENAI_PROVIDER = EmbeddingProviderDefinition(
    id="openai",
    label="OpenAI",
    models=(
        EmbeddingModelDefinition(
            id="text-embedding-3-small",
            label="Text Embedding 3 Small",
            dimensions=1536,
            default=True,
        ),
        EmbeddingModelDefinition(
            id="text-embedding-3-large",
            label="Text Embedding 3 Large",
            dimensions=3072,
        ),
    ),
)

GEMINI_PROVIDER = EmbeddingProviderDefinition(
    id="gemini",
    label="Google Gemini",
    models=(
        EmbeddingModelDefinition(
            id="text-embedding-004",
            label="Text Embedding 004",
            dimensions=768,
            default=True,
        ),
    ),
)

PROVIDERS = (OPENAI_PROVIDER, GEMINI_PROVIDER)


def env_key_for(provider_id: str, settings: Settings) -> str | None:
    if provider_id == "openai":
        return settings.openai_api_key_value
    if provider_id == "gemini":
        return settings.gemini_api_key_value
    return None


def provider_is_available(provider_id: str, settings: Settings) -> bool:
    return env_key_for(provider_id, settings) is not None


def get_model_definition(provider_id: str, model_id: str) -> EmbeddingModelDefinition | None:
    for provider in PROVIDERS:
        if provider.id != provider_id:
            continue
        return next((model for model in provider.models if model.id == model_id), None)
    return None
