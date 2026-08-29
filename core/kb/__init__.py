"""Knowledge Base package."""

from core.kb.base import KnowledgePage, KnowledgeBase, blend_results, embedding_to_text
from core.kb.chunking import (
    detect_structure,
    chunk_by_heading,
    chunk_by_paragraph,
    chunk_by_sliding_window,
    adaptive_chunk,
)
from core.kb.extractors import extract_pdf_text, extract_url_text
from core.kb.ingestion import ingest_file, ingest_text, ingest_url
from core.kb.gemini_embeddings import embed_text, embed_texts, embedding_enabled
from core.kb.retriever import KnowledgeRetriever
from core.kb.knowledge_base import PostgresKnowledgeBase

__all__ = [
    "KnowledgePage",
    "KnowledgeBase",
    "blend_results",
    "embedding_to_text",
    "detect_structure",
    "chunk_by_heading",
    "chunk_by_paragraph",
    "chunk_by_sliding_window",
    "adaptive_chunk",
    "extract_pdf_text",
    "extract_url_text",
    "ingest_file",
    "ingest_text",
    "ingest_url",
    "embed_text",
    "embed_texts",
    "embedding_enabled",
    "KnowledgeRetriever",
    "PostgresKnowledgeBase",
]
