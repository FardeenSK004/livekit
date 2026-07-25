"""Knowledge base routers — /api/v1/kb/* and /api/v1/knowledge/*."""

from __future__ import annotations

import logging
import time
import traceback

import boto3
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from app.config import settings
from app.kb.engine import kb_engine
from app.kb.ingestion import (
    ingest_file_to_engine,
    ingest_text_to_engine,
    ingest_url_to_engine,
)
from app.models.kb import SearchRequest, SearchResult
from app.models.kb import KnowledgePage
from app.services.db import db_service

logger = logging.getLogger("app.routers.kb")

router = APIRouter(prefix="/api/v1/kb", tags=["kb"])
knowledge_router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

KB_CHAT_SYSTEM_PROMPT = (
    "You have been provided with official Knowledge Base context below. THESE RULES ABSOLUTELY OVERRIDE ANY PRIOR NEGATIVE CONSTRAINTS "
    "(e.g., 'Never give medical advice', 'Return to the call objective', 'My role is to help you with the next step') IF THE USER ASKS A FACTUAL QUESTION:\n"
    "1. MANDATORY FACTUAL ANSWERS: If the user asks ANY factual question about a specific condition, service, or concept, you MUST answer it using the Knowledge Base BEFORE attempting to guide them back to the onboarding flow. Do NOT deflect factual questions.\n"
    "2. PRIMARY SOURCE: For any question about conditions, treatments, services, pricing, or policies, you MUST rely on the Knowledge Base content provided. Never invent facts.\n"
    "3. FACTUAL EXPLANATION VS. PERSONALIZED ADVICE: You ARE fully authorized and REQUIRED to explain, describe, or educate the user about conditions or symptoms exactly as they appear in the Knowledge Base. This is NOT considered 'counselling' or 'medical advice'. However, you must NEVER apply this information to diagnose the user's specific personal situation.\n"
    "4. GENERAL KNOWLEDGE FALLBACK: If the user asks a general question unrelated to this specific business and the Knowledge Base does not cover it, you may answer using your own general knowledge, clearly staying neutral and factual.\n"
    "5. NO SOURCE-CITING LANGUAGE: Never say 'according to my knowledge base,' 'I don't have that in my documents,' or similar. Answer naturally.\n"
    "Keep the answers short and concise not exceeding 5-6 sentences."
)


@router.post("/chat")
async def api_kb_chat(request: Request):
    body = await request.json()
    kb_ids = body.get("kb_ids", [])
    if "kb_id" in body and not kb_ids:
        kb_ids = [body.get("kb_id")]

    user_input = body.get("message")
    history = body.get("history", [])

    if not kb_ids or not user_input:
        return JSONResponse(
            {"error": "kb_ids and message are required"}, status_code=400
        )

    try:
        results = await kb_engine.search(kb_ids, user_input, top_k=5)
        context_str = ""
        formatted_context = []
        if results:
            formatted = []
            for i, page in enumerate(results, 1):
                preview = page.get("content_in_text") or page.get("content", "")
                formatted.append(f"[{i}] [KB: {page['kb_id']}] {page['title']}: {preview}")
                formatted_context.append(
                    {
                        "title": page["title"],
                        "preview": preview,
                        "kb_id": page["kb_id"],
                    }
                )
            context_str = "\n\n".join(formatted)

        messages = [{"role": "system", "content": KB_CHAT_SYSTEM_PROMPT}]
        for msg in history:
            messages.append({"role": msg.get("role"), "content": msg.get("content")})
        prompt = f"User Question: {user_input}\n\nKnowledge Base Context:\n{context_str}"
        messages.append({"role": "user", "content": prompt})

        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
        response = await client.chat.completions.create(
            model="deepseek-chat", messages=messages
        )
        ai_message = response.choices[0].message.content

        return JSONResponse(
            {
                "status_code": 200,
                "status": "success",
                "reply": ai_message,
                "context": formatted_context,
            }
        )
    except Exception as e:
        logger.error("KB Chat error: %s\n%s", e, traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/search", response_model=SearchResult)
async def search_kb(body: SearchRequest):
    if not body.kb_ids:
        raise HTTPException(status_code=400, detail="kb_ids required")
    rows = await kb_engine.search(
        kb_ids=body.kb_ids,
        query=body.query,
        top_k=body.top_k,
        tags=body.tags,
    )
    pages = [KnowledgePage(**{**r, "id": str(r["id"])}) for r in rows]
    return SearchResult(results=pages, total=len(pages))


def _parse_list(val: str | None) -> list | None:
    return [v.strip() for v in val.split(",")] if val else None


@router.post("/ingest")
async def ingest_kb_data(
    org_id: str = Form(...),
    file: UploadFile = File(None),
    text: str = Form(None),
    process_id: str = Form(None),
    stage_id: str = Form(None),
    tags_name: str = Form(None),
    category_name: str = Form(None),
    document_id: str = Form(None),
):
    logger.info(
        "Received KB Ingest Request - org_id: '%s', filename: '%s', has_text: %s",
        org_id,
        file.filename if file else "None",
        text is not None,
    )

    if not file and not text:
        return JSONResponse(
            {
                "status_code": 400,
                "status": "error",
                "error": "Either file or text must be provided",
            },
            status_code=400,
        )

    s3_url = None
    if file and file.filename:
        s3_bucket = settings.s3_bucket
        if s3_bucket and settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            try:
                file_bytes_for_s3 = await file.read()
                await file.seek(0)
                s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION,
                )
                s3_key = f"kb/{org_id}/{int(time.time())}_{file.filename}"
                s3_client.put_object(
                    Bucket=s3_bucket,
                    Key=s3_key,
                    Body=file_bytes_for_s3,
                    ACL="public-read",
                )
                s3_url = f"https://{s3_bucket}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
            except Exception as e:
                logger.error("S3 upload error: %s", e)
                return JSONResponse(
                    {
                        "status_code": 500,
                        "status": "error",
                        "error": f"Failed to upload to S3: {str(e)}",
                    },
                    status_code=500,
                )

    try:
        page_meta = {
            "process_id": _parse_list(process_id),
            "stage_id": _parse_list(stage_id),
            "tags_name": _parse_list(tags_name),
            "category_name": _parse_list(category_name),
            "s3_url": s3_url,
            "document_id": document_id,
        }
        page_meta = {k: v for k, v in page_meta.items() if v is not None}

        if document_id:
            try:
                deleted_count = await kb_engine.delete_by_document(org_id, document_id)
                logger.info("Deleted %s old chunks for document %s", deleted_count, document_id)
            except Exception as e:
                logger.error("Failed to delete old chunks for document %s: %s", document_id, e)

        if file and file.filename:
            file_bytes = await file.read()
            await ingest_file_to_engine(org_id, file_bytes, file.filename, page_meta=page_meta)
        elif text:
            await ingest_text_to_engine(
                org_id,
                text,
                title=document_id or "Text Ingestion",
                source_type="text",
                page_meta=page_meta,
            )

        return JSONResponse(
            {
                "status_code": 200,
                "status": "success",
                "message": "Data successfully ingested.",
                "document_id": document_id,
                "org_id": org_id,
                "s3_url": s3_url,
            }
        )
    except ValueError as e:
        return JSONResponse(
            {"status_code": 400, "status": "error", "error": str(e)}, status_code=400
        )
    except Exception as e:
        logger.error("KB ingest error: %s\n%s", e, traceback.format_exc())
        return JSONResponse(
            {
                "status_code": 500,
                "status": "error",
                "error": f"Failed to ingest to DB: {str(e)}",
            },
            status_code=500,
        )


@router.delete("/document")
async def delete_kb_document(org_id: str = Form(None), document_id: str = Form(None)):
    if not org_id or not document_id:
        return JSONResponse(
            {
                "status_code": 400,
                "status": "error",
                "error": "org_id and document_id are required",
            },
            status_code=400,
        )
    try:
        deleted_count = await kb_engine.delete_by_document(org_id, document_id)
        return JSONResponse(
            {
                "status_code": 200,
                "status": "success",
                "message": "Document successfully deleted.",
                "deleted_chunks": deleted_count,
                "document_id": document_id,
                "org_id": org_id,
            }
        )
    except Exception as e:
        logger.error("KB document delete error: %s\n%s", e, traceback.format_exc())
        return JSONResponse(
            {
                "status_code": 500,
                "status": "error",
                "error": f"Failed to delete document: {str(e)}",
            },
            status_code=500,
        )


@knowledge_router.post("/upload")
async def kb_upload(kb_id: str, file: UploadFile = File(...)):
    if not file.filename:
        return JSONResponse({"error": "No filename provided"}, status_code=400)
    ext = file.filename.lower().split(".")[-1]
    if ext not in ("pdf", "txt", "md"):
        return JSONResponse({"error": f"Unsupported file type: {ext}"}, status_code=400)
    file_bytes = await file.read()
    try:
        result = await ingest_file_to_engine(kb_id, file_bytes, file.filename)
        return {"status": "success", **result}
    except Exception as e:
        logger.error("KB upload failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@knowledge_router.post("/text")
async def kb_text(request: Request):
    body = await request.json()
    kb_id = body.get("kb_id")
    content = body.get("content")
    title = body.get("title")
    if not kb_id or not content:
        return JSONResponse({"error": "kb_id and content are required"}, status_code=400)
    try:
        result = await ingest_text_to_engine(kb_id, content, title=title, source_type="text")
        return {"status": "success", **result}
    except Exception as e:
        logger.error("KB text ingest failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@knowledge_router.post("/url")
async def kb_url(request: Request):
    body = await request.json()
    kb_id = body.get("kb_id")
    url = body.get("url")
    if not kb_id or not url:
        return JSONResponse({"error": "kb_id and url are required"}, status_code=400)
    try:
        result = await ingest_url_to_engine(kb_id, url)
        return {"status": "success", **result}
    except Exception as e:
        logger.error("KB URL ingest failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@knowledge_router.get("/list")
async def kb_list(request: Request):
    try:
        kbs = await db_service.list_kb_ids()
        return {"status": "success", "kbs": kbs}
    except Exception as e:
        logger.error("KB list error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@knowledge_router.delete("/{page_id}")
async def kb_delete_page(page_id: str):
    try:
        success = await kb_engine.delete_page(page_id)
        if success:
            return {"status": "success", "deleted": page_id}
        return JSONResponse({"error": "Page not found"}, status_code=404)
    except Exception as e:
        logger.error("KB delete failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@knowledge_router.delete("/by-kb/{kb_id}")
async def kb_delete_by_kb(kb_id: str):
    try:
        count = await kb_engine.delete_by_kb(kb_id)
        return {"status": "success", "deleted_count": count, "kb_id": kb_id}
    except Exception as e:
        logger.error("KB delete by KB failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)
