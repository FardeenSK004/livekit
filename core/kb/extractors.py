"""PDF and URL text extraction helpers."""

import io
import logging
from pypdf import PdfReader
import trafilatura

logger = logging.getLogger("core.kb.extractors")


async def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract raw plain text from PDF bytes."""
    reader = PdfReader(io.BytesIO(file_bytes))
    extracted = []
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            extracted.append(txt)
    return "\n\n".join(extracted)


async def extract_url_text(url: str) -> str:
    """Fetch and extract cleaned article text from a public web URL."""
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError(f"Failed to fetch content from URL: {url}")
    text = trafilatura.extract(
        downloaded,
        include_links=False,
        include_images=False,
        output_format="txt",
    )
    if not text:
        raise ValueError(f"No extractable text found at URL: {url}")
    return text
