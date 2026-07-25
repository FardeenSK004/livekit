"""KB ingestion helpers — ported from mantra/knowledge_base.py."""

from __future__ import annotations

import asyncio
import io
import re
import uuid
from typing import Optional

import trafilatura
from pypdf import PdfReader

from app.kb.chunker import adaptive_chunk
from app.kb.engine import PostgresKnowledgeBase, kb_engine


async def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    texts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            texts.append(t)
    return "\n\n".join(texts)


async def extract_url_text(url: str) -> str:
    downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
    if not downloaded:
        raise ValueError(f"Failed to fetch URL: {url}")

    extracted = trafilatura.extract(
        downloaded, include_comments=False, include_tables=True, favor_recall=True
    )

    raw_text = re.sub(
        r"<(script|style|head|svg|nav|footer)[^>]*>.*?</\1>",
        " ",
        downloaded,
        flags=re.DOTALL | re.IGNORECASE,
    )
    raw_text = re.sub(r"<[^>]+>", " ", raw_text)
    raw_text = re.sub(r"\s+", " ", raw_text).strip()

    if not extracted or len(raw_text) > len(extracted or "") * 2:
        extracted = raw_text

    if not extracted:
        raise ValueError(f"No readable content found at URL: {url}")
    return extracted


async def ingest_file(
    kb: PostgresKnowledgeBase,
    kb_id: str,
    file_bytes: bytes,
    filename: str,
    page_meta: Optional[dict] = None,
) -> dict:
    if filename.lower().endswith(".pdf"):
        text = await extract_pdf_text(file_bytes)
    elif filename.lower().endswith((".txt", ".md")):
        text = file_bytes.decode("utf-8")
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    return await ingest_text(
        kb,
        kb_id,
        text,
        source_type="file",
        content=filename,
        page_meta=page_meta,
    )


async def ingest_text(
    kb: PostgresKnowledgeBase,
    kb_id: str,
    content_in_text: str,
    title: Optional[str] = None,
    source_type: str = "text",
    content: str = "",
    page_meta: Optional[dict] = None,
) -> dict:
    chunks = adaptive_chunk(content_in_text)
    page_ids = []
    for i, chunk in enumerate(chunks):
        meta = {
            "strategy": chunk["strategy"],
            "chunk_index": i,
            "total_chunks": len(chunks),
        }
        if page_meta:
            meta.update(page_meta)

        page_id = await kb.add_page(
            kb_id=kb_id,
            title=title or chunk["heading"],
            content=content,
            content_in_text=chunk["content"],
            source_type=source_type,
            page_meta=meta,
        )
        page_ids.append(page_id)

    return {
        "chunks_created": len(chunks),
        "strategy_used": chunks[0]["strategy"] if chunks else "unknown",
        "page_ids": page_ids,
        "kb_id": kb_id,
    }


async def ingest_url(kb: PostgresKnowledgeBase, kb_id: str, url: str) -> dict:
    text = await extract_url_text(url)
    return await ingest_text(kb, kb_id, text, source_type="url", content=url)


# Default engine-backed helpers for routers
async def ingest_file_to_engine(
    kb_id: str, file_bytes: bytes, filename: str, page_meta: Optional[dict] = None
) -> dict:
    return await ingest_file(kb_engine, kb_id, file_bytes, filename, page_meta=page_meta)


async def ingest_text_to_engine(
    kb_id: str,
    content: str,
    title: Optional[str] = None,
    source_type: str = "text",
    page_meta: Optional[dict] = None,
) -> dict:
    return await ingest_text(
        kb_engine,
        kb_id,
        content,
        title=title,
        source_type=source_type,
        page_meta=page_meta,
    )


async def ingest_url_to_engine(kb_id: str, url: str) -> dict:
    return await ingest_url(kb_engine, kb_id, url)
