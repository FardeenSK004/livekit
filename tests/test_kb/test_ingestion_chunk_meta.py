from app.kb.chunker import adaptive_chunk


def test_adaptive_chunk_returns_mantra_shape():
    text = "# Intro\nHello world\n## Details\nMore content here about services."
    chunks = adaptive_chunk(text, max_tokens=50)
    assert chunks
    assert "content" in chunks[0]
    assert "heading" in chunks[0]
    assert "strategy" in chunks[0]
