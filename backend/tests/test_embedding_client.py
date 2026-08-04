from __future__ import annotations

import httpx
import pytest

from app.knowledge.embeddings import EmbeddingProviderError, OpenAIEmbeddingClient


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"error": {"message": "secret provider detail"}}),
        httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]}),
        httpx.Response(
            200,
            content=b'{"data":[{"index":0,"embedding":[NaN,NaN,NaN]}]}',
            headers={"content-type": "application/json"},
        ),
        httpx.Response(200, json={"data": ["not-an-object"]}),
    ],
)
async def test_embedding_failures_are_validated_and_sanitized(response: httpx.Response) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response)
    ) as http_client:
        client = OpenAIEmbeddingClient(api_key="secret-key", http_client=http_client)
        with pytest.raises(EmbeddingProviderError) as raised:
            await client.embed(["fixture"], model_id="model", expected_dimensions=3)

    message = str(raised.value)
    assert "secret-key" not in message
    assert "secret provider detail" not in message
