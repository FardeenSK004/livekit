"""Adaptive document chunker — heading, paragraph, or sliding-window.

Extracted from mantra/knowledge_base.py chunking helpers.
"""

from __future__ import annotations

from typing import Any


def detect_structure(text: str) -> str:
    """Detect document structure: 'heading', 'paragraph', or 'dense'."""
    lines = text.split("\n")
    heading_count = sum(
        1
        for line in lines
        if line.strip().startswith(
            ("#", "##", "###", "Section", "SECTION", "Chapter", "CHAPTER")
        )
    )
    paragraph_count = sum(1 for line in lines if len(line.strip()) > 50)

    if heading_count >= 2:
        return "heading"
    if paragraph_count >= 3:
        return "paragraph"
    return "dense"


def chunk_by_heading(text: str, max_tokens: int = 2000) -> list[dict]:
    chunks: list[dict] = []
    current_chunk: list[str] = []
    current_heading = "Introduction"
    current_tokens = 0

    for line in text.split("\n"):
        line_stripped = line.strip()
        is_heading = line_stripped.startswith(
            ("#", "##", "###", "Section", "SECTION", "Chapter", "CHAPTER")
        )

        if is_heading and current_chunk:
            chunks.append(
                {
                    "content": "\n".join(current_chunk).strip(),
                    "heading": current_heading,
                    "strategy": "heading",
                }
            )
            current_chunk = [line]
            current_heading = line_stripped.lstrip("#").strip()
            current_tokens = len(line) // 4
        else:
            current_chunk.append(line)
            current_tokens += len(line) // 4
            if current_tokens > max_tokens:
                chunks.append(
                    {
                        "content": "\n".join(current_chunk).strip(),
                        "heading": current_heading,
                        "strategy": "heading",
                    }
                )
                current_chunk = []
                current_tokens = 0

    if current_chunk:
        chunks.append(
            {
                "content": "\n".join(current_chunk).strip(),
                "heading": current_heading,
                "strategy": "heading",
            }
        )
    return chunks


def chunk_by_paragraph(text: str, max_tokens: int = 2000) -> list[dict]:
    chunks: list[dict] = []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    current_chunk: list[str] = []
    current_tokens = 0

    for paragraph in paragraphs:
        p_tokens = len(paragraph) // 4
        if current_tokens + p_tokens > max_tokens and current_chunk:
            chunks.append(
                {
                    "content": "\n\n".join(current_chunk),
                    "heading": f"Section {len(chunks) + 1}",
                    "strategy": "paragraph",
                }
            )
            current_chunk = [paragraph]
            current_tokens = p_tokens
        else:
            current_chunk.append(paragraph)
            current_tokens += p_tokens

    if current_chunk:
        chunks.append(
            {
                "content": "\n\n".join(current_chunk),
                "heading": f"Section {len(chunks) + 1}",
                "strategy": "paragraph",
            }
        )
    return chunks


def chunk_by_sliding_window(
    text: str, max_tokens: int = 2000, overlap: int = 200
) -> list[dict]:
    words = text.split()
    # Approx 1 token ≈ 0.75 words; use chars//4 style via word windows
    window = max(max_tokens, 1)
    step = max(window - overlap, 1)
    chunks: list[dict] = []
    i = 0
    idx = 1
    while i < len(words):
        piece = words[i : i + window]
        if not piece:
            break
        chunks.append(
            {
                "content": " ".join(piece),
                "heading": f"Section {idx}",
                "strategy": "sliding_window",
            }
        )
        i += step
        idx += 1
    return chunks


def chunk_document(
    text: str,
    title: str = "",
    max_chunk_size: int = 2000,
) -> list[dict[str, Any]]:
    """Adaptively chunk a document based on its structure."""
    structure = detect_structure(text)
    if structure == "heading":
        raw = chunk_by_heading(text, max_tokens=max_chunk_size)
    elif structure == "paragraph":
        raw = chunk_by_paragraph(text, max_tokens=max_chunk_size)
    else:
        raw = chunk_by_sliding_window(text, max_tokens=max_chunk_size)

    results = []
    for i, chunk in enumerate(raw):
        content = chunk.get("content", "")
        heading = chunk.get("heading", title) or title
        results.append(
            {
                "title": f"{title} (part {i + 1})" if len(raw) > 1 and title else heading,
                "content": content,
                "meta": {
                    "chunking_strategy": chunk.get("strategy", structure),
                    "chunk_index": i,
                    "heading": heading,
                },
            }
        )
    return results


def adaptive_chunk(text: str, max_tokens: int = 2000) -> list[dict]:
    """Auto-detect structure and apply appropriate chunking (mantra-compatible)."""
    structure = detect_structure(text)
    if structure == "heading":
        return chunk_by_heading(text, max_tokens=max_tokens)
    if structure == "paragraph":
        return chunk_by_paragraph(text, max_tokens=max_tokens)
    return chunk_by_sliding_window(text, max_tokens=max_tokens)
