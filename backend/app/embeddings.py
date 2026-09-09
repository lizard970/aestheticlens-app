import math
import os
from dataclasses import dataclass
from typing import Protocol

import httpx


EMBEDDING_DIMENSIONS = 1536


class EmbeddingError(RuntimeError):
    pass


class EmbeddingAdapter(Protocol):
    model_name: str

    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class OpenAIEmbeddingSettings:
    api_key: str
    model: str = "text-embedding-3-small"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls):
        return cls(
            api_key=os.getenv("AESTHETICLENS_EMBEDDING_API_KEY", "").strip(),
            model=os.getenv("AESTHETICLENS_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
            base_url=os.getenv("AESTHETICLENS_EMBEDDING_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            timeout_seconds=float(os.getenv("AESTHETICLENS_EMBEDDING_TIMEOUT_SECONDS", "30")),
        )


class OpenAIEmbeddingAdapter:
    def __init__(self, settings: OpenAIEmbeddingSettings) -> None:
        if not settings.api_key or not settings.model:
            raise ValueError("EMBEDDING_CONFIGURATION_INCOMPLETE")
        self.settings = settings
        self.model_name = settings.model

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingError("EMBEDDING_INPUT_EMPTY")
        try:
            response = httpx.post(
                f"{self.settings.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.settings.api_key}"},
                json={"input": text, "model": self.settings.model,
                      "encoding_format": "float", "dimensions": EMBEDDING_DIMENSIONS},
                timeout=self.settings.timeout_seconds,
            )
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise EmbeddingError("EMBEDDING_PROVIDER_FAILED") from exc
        if (not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS
                or any(type(value) not in {int, float} or not math.isfinite(value) for value in vector)):
            raise EmbeddingError("EMBEDDING_RESPONSE_INVALID")
        return [float(value) for value in vector]


def configured_embedding_adapter() -> EmbeddingAdapter | None:
    provider = os.getenv("AESTHETICLENS_EMBEDDING_PROVIDER", "").strip().lower()
    if not provider:
        return None
    if provider != "openai":
        raise ValueError("UNSUPPORTED_EMBEDDING_PROVIDER")
    return OpenAIEmbeddingAdapter(OpenAIEmbeddingSettings.from_env())
