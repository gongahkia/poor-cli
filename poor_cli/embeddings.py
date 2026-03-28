"""
Embedding providers for poor-cli semantic search.

Supports multiple backends for generating text embeddings:
- Gemini: text-embedding-004
- OpenAI: text-embedding-3-small
- Ollama: nomic-embed-text (local, free)

Embeddings are stored as JSON-serialized float arrays in SQLite.
Cosine similarity is computed in Python for portability.
"""

from __future__ import annotations

import json
import math
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

EMBEDDING_DIMS = {
    "gemini": 768,
    "openai": 1536,
    "ollama": 768,
}


class EmbeddingProvider(ABC):
    """Abstract base for embedding generation."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        ...

    @abstractmethod
    def available(self) -> bool:
        """Check if this provider is configured and available."""
        ...


class GeminiEmbedding(EmbeddingProvider):
    """Google Gemini text-embedding-004."""

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def dimensions(self) -> int:
        return 768

    def available(self) -> bool:
        return bool(os.environ.get("GEMINI_API_KEY"))

    async def embed(self, texts: List[str]) -> List[List[float]]:
        try:
            from google import genai
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            results = []
            # batch in groups of 100
            for i in range(0, len(texts), 100):
                batch = texts[i:i + 100]
                response = client.models.embed_content(
                    model="text-embedding-004",
                    contents=batch,
                )
                for emb in response.embeddings:
                    results.append(list(emb.values))
            return results
        except Exception as exc:
            logger.error("gemini embedding failed: %s", exc)
            return [[] for _ in texts]


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI text-embedding-3-small."""

    @property
    def name(self) -> str:
        return "openai"

    @property
    def dimensions(self) -> int:
        return 1536

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    async def embed(self, texts: List[str]) -> List[List[float]]:
        try:
            import openai
            client = openai.AsyncOpenAI()
            results = []
            for i in range(0, len(texts), 2048):
                batch = texts[i:i + 2048]
                response = await client.embeddings.create(
                    model="text-embedding-3-small",
                    input=batch,
                )
                for item in response.data:
                    results.append(item.embedding)
            return results
        except Exception as exc:
            logger.error("openai embedding failed: %s", exc)
            return [[] for _ in texts]


class OllamaEmbedding(EmbeddingProvider):
    """Ollama nomic-embed-text (local, free)."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def dimensions(self) -> int:
        return 768

    def available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def embed(self, texts: List[str]) -> List[List[float]]:
        try:
            import aiohttp
            results = []
            async with aiohttp.ClientSession() as session:
                for text in texts:
                    async with session.post(
                        f"{self._base_url}/api/embed",
                        json={"model": "nomic-embed-text", "input": text},
                    ) as resp:
                        data = await resp.json()
                        embeddings = data.get("embeddings", [[]])
                        results.append(embeddings[0] if embeddings else [])
            return results
        except Exception as exc:
            logger.error("ollama embedding failed: %s", exc)
            return [[] for _ in texts]


def get_embedding_provider(preferred: Optional[str] = None) -> Optional[EmbeddingProvider]:
    """Get the best available embedding provider."""
    providers = [GeminiEmbedding(), OpenAIEmbedding(), OllamaEmbedding()]
    if preferred:
        for p in providers:
            if p.name == preferred and p.available():
                return p
    for p in providers:
        if p.available():
            return p
    return None


# ── vector math ──────────────────────────────────────────────────────────

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def rank_by_similarity(
    query_embedding: List[float],
    candidates: List[Tuple[Any, List[float]]],
    top_k: int = 10,
) -> List[Tuple[Any, float]]:
    """Rank candidates by cosine similarity to query embedding."""
    scored = []
    for item, emb in candidates:
        if emb:
            score = cosine_similarity(query_embedding, emb)
            scored.append((item, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
