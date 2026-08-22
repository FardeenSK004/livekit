"""
Google Gemini embedding client for KB semantic search (Tier 2).

Uses `gemini-embedding-2` (verified working with the configured
GOOGLE_API_KEY). Provides batched, retrying embedding of texts for both
ingestion (chunk storage) and query-time search.

Model and dimension are configurable via env:
  - KB_EMBEDDING_MODEL  (default: gemini-embedding-2)
  - KB_EMBEDDING_DIM    (default: 1536)

NOTE: dimension is 1536 (not the model's native 3072) because pgvector
HNSW/IVFFlat indexes cap at 2000 dimensions.
"""

import logging
import asyncio
from typing import Optional

logger = logging.getLogger("mantra.gemini_embeddings")

_BATCH_SIZE = 100
_MAX_RETRIES = 3
_client = None


def _get_client():
    """Lazy singleton google.genai.Client."""
    global _client
    if _client is None:
        from google.genai import Client
        import os
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set — cannot compute embeddings")
        _client = Client(api_key=api_key)
    return _client


def get_embedding_model() -> str:
    import os
    return os.getenv("KB_EMBEDDING_MODEL", "gemini-embedding-2").strip()


def get_embedding_dim() -> int:
    import os
    return int(os.getenv("KB_EMBEDDING_DIM", "1536"))


def embedding_enabled() -> bool:
    """True if embeddings can be computed (API key present + model reachable later)."""
    import os
    return bool(os.getenv("GOOGLE_API_KEY", "").strip())


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts.

    Returns a list aligned with the input order. Raises if the API key is
    missing or the request ultimately fails after retries.
    """
    if not texts:
        return []

    client = _get_client()
    from google.genai import types

    results: list[list[float]] = []

    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start:start + _BATCH_SIZE]
        contents = [types.Content(parts=[types.Part(text=t)]) for t in batch]

        last_err: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.aio.models.embed_content(
                    model=get_embedding_model(),
                    contents=contents,
                    config=types.EmbedContentConfig(
                        output_dimensionality=get_embedding_dim(),
                    ),
                )
                for emb in resp.embeddings:
                    results.append(list(emb.values))
                break
            except Exception as e:  # noqa: BLE001 — retry any transient failure
                last_err = e
                wait = 2 ** attempt
                logger.warning(
                    f"Embedding attempt {attempt + 1}/{_MAX_RETRIES} failed for "
                    f"{len(batch)} texts ({e}); retrying in {wait}s"
                )
                await asyncio.sleep(wait)
        else:
            raise RuntimeError(f"Embedding failed after {_MAX_RETRIES} attempts: {last_err}")

    return results


async def embed_text(text: str) -> Optional[list[float]]:
    """Embed a single text; returns None on failure (caller falls back to FTS-only)."""
    try:
        result = await embed_texts([text])
        return result[0] if result else None
    except Exception as e:  # noqa: BLE001
        logger.error(f"embed_text failed, continuing FTS-only: {e}")
        return None
