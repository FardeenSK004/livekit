from app.kb.chunker import chunk_document, detect_structure


def test_detect_heading_structure():
    text = "# One\ncontent\n## Two\nmore content\n### Three\neven more"
    assert detect_structure(text) == "heading"


def test_chunk_document_paragraph():
    text = "\n\n".join(["word " * 30 for _ in range(5)])
    chunks = chunk_document(text, title="Doc", max_chunk_size=200)
    assert len(chunks) >= 1
    assert "content" in chunks[0]
