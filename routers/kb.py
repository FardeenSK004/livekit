"""Knowledge Base API routes."""

from fastapi import APIRouter, Request, UploadFile, File
from controllers.kb import kb_controller

router = APIRouter(tags=["Knowledge Base"])


@router.post("/api/v1/kb/chat")
async def api_kb_chat(request: Request):
    """Text-based chat endpoint for testing the KB."""
    return await kb_controller.chat(request)


@router.post("/api/v1/kb/ingest")
async def ingest_kb_data(request: Request):
    """Ingest endpoint for MantraAssist KB data."""
    return await kb_controller.ingest(request)


@router.post("/api/v1/kb/backfill-embeddings")
async def backfill_kb_embeddings(request: Request):
    """Compute and store missing vector embeddings for KB pages."""
    return await kb_controller.backfill_embeddings(request)


@router.delete("/api/v1/kb/document")
async def delete_kb_document(request: Request):
    """Delete all chunks for a document from a knowledge base."""
    return await kb_controller.delete_document(request)


@router.post("/api/v1/knowledge/upload")
async def kb_upload(request: Request, kb_id: str, file: UploadFile = File(...)):
    """Upload and ingest a document file."""
    return await kb_controller.upload_file(kb_id, file)


@router.post("/api/v1/knowledge/text")
async def kb_text(request: Request):
    """Ingest raw text content into KB."""
    return await kb_controller.ingest_text_endpoint(request)


@router.post("/api/v1/knowledge/url")
async def kb_url(request: Request):
    """Fetch and ingest content from a URL into KB."""
    return await kb_controller.ingest_url_endpoint(request)


@router.get("/api/v1/knowledge/list")
async def kb_list(request: Request):
    """List ingested KB pages."""
    return await kb_controller.list_knowledge(request)


@router.delete("/api/v1/knowledge/{page_id}")
async def kb_delete_page(page_id: str):
    """Delete a specific KB page chunk."""
    return await kb_controller.delete_page(page_id)


@router.delete("/api/v1/knowledge/by-kb/{kb_id}")
async def kb_delete_by_kb(kb_id: str):
    """Delete all pages belonging to a specific kb_id."""
    return await kb_controller.delete_by_kb(kb_id)
