from __future__ import annotations

import math
from collections.abc import Sequence

import httpx


class EmbeddingProviderError(RuntimeError):
    pass


class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        http_client: httpx.AsyncClient,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._api_key = api_key
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model_id: str,
        expected_dimensions: int,
    ) -> list[list[float]]:
        if not self._api_key:
            raise EmbeddingProviderError("OpenAI embedding provider is unavailable")
        if not texts:
            return []
        try:
            response = await self._http_client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": model_id, "input": list(texts)},
                timeout=30.0,
                follow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            raw_items = payload.get("data")
            if not isinstance(raw_items, list) or len(raw_items) != len(texts):
                raise EmbeddingProviderError("Embedding provider returned an invalid batch")
            if not all(isinstance(item, dict) for item in raw_items):
                raise EmbeddingProviderError("Embedding provider returned an invalid batch")
            ordered = sorted(raw_items, key=lambda item: item.get("index", -1))
            if [item.get("index") for item in ordered] != list(range(len(texts))):
                raise EmbeddingProviderError("Embedding provider returned invalid vector indices")
            vectors: list[list[float]] = []
            for item in ordered:
                raw_vector = item.get("embedding") if isinstance(item, dict) else None
                if not isinstance(raw_vector, list) or len(raw_vector) != expected_dimensions:
                    raise EmbeddingProviderError(
                        "Embedding provider returned an unexpected vector dimension"
                    )
                vector = [float(value) for value in raw_vector]
                if not all(math.isfinite(value) for value in vector):
                    raise EmbeddingProviderError("Embedding provider returned a non-finite value")
                vectors.append(vector)
            return vectors
        except EmbeddingProviderError:
            raise
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError("Embedding provider request failed") from exc


class GeminiEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        http_client: httpx.AsyncClient,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self._api_key = api_key
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model_id: str,
        expected_dimensions: int,
    ) -> list[list[float]]:
        if not self._api_key:
            raise EmbeddingProviderError("Gemini embedding provider is unavailable")
        if not texts:
            return []
        try:
            response = await self._http_client.post(
                f"{self._base_url}/models/{model_id}:batchEmbedContents",
                headers={"x-goog-api-key": self._api_key},
                json={
                    "requests": [
                        {
                            "model": f"models/{model_id}",
                            "content": {"parts": [{"text": text}]},
                        }
                        for text in texts
                    ]
                },
                timeout=30.0,
                follow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
            raw_items = payload.get("embeddings")
            if not isinstance(raw_items, list) or len(raw_items) != len(texts):
                raise EmbeddingProviderError("Embedding provider returned an invalid batch")
            vectors: list[list[float]] = []
            for item in raw_items:
                raw_vector = item.get("values") if isinstance(item, dict) else None
                if not isinstance(raw_vector, list) or len(raw_vector) != expected_dimensions:
                    raise EmbeddingProviderError(
                        "Embedding provider returned an unexpected vector dimension"
                    )
                vector = [float(value) for value in raw_vector]
                if not all(math.isfinite(value) for value in vector):
                    raise EmbeddingProviderError("Embedding provider returned a non-finite value")
                vectors.append(vector)
            return vectors
        except EmbeddingProviderError:
            raise
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError("Embedding provider request failed") from exc


class EmbeddingClientFactory:
    """Builds a provider client bound to a specific API key.

    Keys can come from the environment or from a per-user stored key, so
    clients are constructed per call rather than once at startup.
    """

    def __init__(self, *, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    def client_for(self, provider_id: str, api_key: str):
        if provider_id == "openai":
            return OpenAIEmbeddingClient(api_key=api_key, http_client=self._http_client)
        if provider_id == "gemini":
            return GeminiEmbeddingClient(api_key=api_key, http_client=self._http_client)
        raise EmbeddingProviderError(f"Unknown embedding provider: {provider_id}")
