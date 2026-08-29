"""Document text structure detection and chunking algorithms."""

import re


def detect_structure(text: str) -> str:
    """Detect whether document has markdown headings, distinct paragraphs, or raw prose."""
    heading_count = len(re.findall(r"^#{1,6}\s+.+", text, re.MULTILINE))
    if heading_count >= 3:
        return "structured"

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) >= 4:
        return "semi_structured"

    return "unstructured"


def chunk_by_heading(text: str, max_tokens: int = 2000) -> list[dict]:
    """Split text by markdown headings with fallback to paragraph splitting."""
    pattern = r"^(#{1,6}\s+.+)$"
    parts = re.split(pattern, text, flags=re.MULTILINE)

    chunks = []
    current_title = "Introduction"
    current_body = ""

    for part in parts:
        part_stripped = part.strip()
        if not part_stripped:
            continue

        if re.match(r"^#{1,6}\s+", part_stripped):
            if current_body.strip():
                chunks.append({"title": current_title, "content": current_body.strip()})
            current_title = re.sub(r"^#{1,6}\s+", "", part_stripped)
            current_body = ""
        else:
            current_body += part + "\n"

    if current_body.strip():
        chunks.append({"title": current_title, "content": current_body.strip()})

    final_chunks = []
    for chunk in chunks:
        approx_tokens = len(chunk["content"].split()) * 1.3
        if approx_tokens > max_tokens:
            sub_chunks = chunk_by_paragraph(chunk["content"], max_tokens=max_tokens)
            for i, sc in enumerate(sub_chunks, 1):
                final_chunks.append({
                    "title": f"{chunk['title']} (Part {i})",
                    "content": sc["content"],
                })
        else:
            final_chunks.append(chunk)

    return final_chunks or [{"title": "Document", "content": text.strip()}]


def chunk_by_paragraph(text: str, max_tokens: int = 2000) -> list[dict]:
    """Group paragraphs together until max_tokens budget is reached."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks = []
    current_chunk: list[str] = []
    current_tokens = 0

    for p in paragraphs:
        p_tokens = len(p.split()) * 1.3
        if current_tokens + p_tokens > max_tokens and current_chunk:
            combined = "\n\n".join(current_chunk)
            first_line = current_chunk[0].split("\n")[0][:60]
            chunks.append({
                "title": f"Section: {first_line}",
                "content": combined,
            })
            current_chunk = [p]
            current_tokens = p_tokens
        else:
            current_chunk.append(p)
            current_tokens += p_tokens

    if current_chunk:
        combined = "\n\n".join(current_chunk)
        first_line = current_chunk[0].split("\n")[0][:60]
        chunks.append({
            "title": f"Section: {first_line}",
            "content": combined,
        })

    return chunks


def chunk_by_sliding_window(
    text: str, max_tokens: int = 2000, overlap_tokens: int = 200
) -> list[dict]:
    """Fallback sliding window chunker with token overlap."""
    words = text.split()
    max_words = int(max_tokens / 1.3)
    overlap_words = int(overlap_tokens / 1.3)
    step = max_words - overlap_words

    chunks = []
    for i in range(0, len(words), step):
        window = words[i : i + max_words]
        content = " ".join(window)
        chunks.append({
            "title": f"Section (words {i}-{i+len(window)})",
            "content": content,
        })
        if i + max_words >= len(words):
            break

    return chunks or [{"title": "Document", "content": text.strip()}]


def adaptive_chunk(text: str, max_tokens: int = 2000) -> list[dict]:
    """Automatically select optimal chunking strategy based on text structure."""
    text = text.strip()
    if not text:
        return []

    structure = detect_structure(text)
    if structure == "structured":
        return chunk_by_heading(text, max_tokens=max_tokens)
    elif structure == "semi_structured":
        return chunk_by_paragraph(text, max_tokens=max_tokens)
    else:
        return chunk_by_sliding_window(text, max_tokens=max_tokens)
