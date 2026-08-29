"""KB Ingestion helpers for files, text, and URLs."""

import logging
from typing import Optional, List, Dict, Any
from core.kb.base import KnowledgeBase
from core.kb.chunking import adaptive_chunk
from core.kb.extractors import extract_pdf_text, extract_url_text

logger = logging.getLogger("core.kb.ingestion")


async def ingest_file(
    kb: KnowledgeBase,
    kb_id: str,
    filename: str,
    file_bytes: bytes,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extract, chunk, and ingest document file."""
    if filename.lower().endswith(".pdf"):
        text = await extract_pdf_text(file_bytes)
    else:
        text = file_bytes.decode("utf-8", errors="replace")

    chunks = adaptive_chunk(text)
    page_ids = []
    for chunk in chunks:
        title = f"{filename} - {chunk['title']}"
        meta = {"filename": filename, "source": "file_upload"}
        if tags:
            meta["tags_name"] = tags
        pid = await kb.add_page(
            kb_id=kb_id,
            title=title,
            content=chunk["content"],
            source_type="file",
            page_meta=meta,
        )
        page_ids.append(pid)

    return {
        "status": "success",
        "filename": filename,
        "chunks_created": len(page_ids),
        "page_ids": page_ids,
    }


async def ingest_text(
    kb: KnowledgeBase,
    kb_id: str,
    title: str,
    text: str,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Chunk and ingest raw string text."""
    chunks = adaptive_chunk(text)
    page_ids = []
    for chunk in chunks:
        chunk_title = f"{title} - {chunk['title']}" if len(chunks) > 1 else title
        meta = {"source": "direct_text"}
        if tags:
            meta["tags_name"] = tags
        pid = await kb.add_page(
            kb_id=kb_id,
            title=chunk_title,
            content=chunk["content"],
            source_type="text",
            page_meta=meta,
        )
        page_ids.append(pid)

    return {
        "status": "success",
        "title": title,
        "chunks_created": len(page_ids),
        "page_ids": page_ids,
    }


async def ingest_url(
    kb: KnowledgeBase,
    kb_id: str,
    url: str,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fetch URL, chunk, and store in KB."""
    text = await extract_url_text(url)
    chunks = adaptive_chunk(text)
    page_ids = []
    for chunk in chunks:
        title = f"{url} - {chunk['title']}"
        meta = {"url": url, "source": "url_scraper"}
        if tags:
            meta["tags_name"] = tags
        pid = await kb.add_page(
            kb_id=kb_id,
            title=title,
            content=chunk["content"],
            source_type="url",
            page_meta=meta,
        )
        page_ids.append(pid)

    return {
        "status": "success",
        "url": url,
        "chunks_created": len(page_ids),
        "page_ids": page_ids,
    }
