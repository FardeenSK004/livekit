"""Knowledge Base controllers."""

import os
import json
import logging
import traceback
from typing import List, Optional
from fastapi import Request, UploadFile, File
from fastapi.responses import JSONResponse
import openai

from core.kb.knowledge_base import (
    PostgresKnowledgeBase,
    extract_pdf_text,
    extract_url_text,
    ingest_text,
    ingest_file,
    ingest_url,
)
from dependencies.database import get_db_connection

logger = logging.getLogger("controllers.kb")


def _get_kb_instance() -> PostgresKnowledgeBase:
    dsn = (
        f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    )
    return PostgresKnowledgeBase(dsn)


class KBController:
    """Knowledge base search, ingestion, backfill, and management controller."""

    @staticmethod
    async def chat(request: Request):
        body = await request.json()
        kb_ids = body.get("kb_ids", [])
        if "kb_id" in body and not kb_ids:
            kb_ids = [body.get("kb_id")]

        user_input = body.get("message")
        history = body.get("history", [])

        if not kb_ids or not user_input:
            return JSONResponse({"error": "kb_ids and message are required"}, status_code=400)

        try:
            kb = _get_kb_instance()
            results = await kb.search(kb_ids, user_input, top_k=5)

            context_str = ""
            formatted_context = []
            if results:
                formatted = []
                for i, page in enumerate(results, 1):
                    preview = (
                        page.content_in_text
                        if hasattr(page, "content_in_text")
                        else page.content
                    )
                    formatted.append(f"[{i}] [KB: {page.kb_id}] {page.title}: {preview}")
                    formatted_context.append({
                        "title": page.title,
                        "preview": preview,
                        "kb_id": page.kb_id,
                    })
                context_str = "\n\n".join(formatted)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You have been provided with official Knowledge Base context below. Answer accurately using provided context."
                    ),
                }
            ]
            for msg in history:
                messages.append({"role": msg.get("role"), "content": msg.get("content")})

            prompt = f"User Question: {user_input}\n\nKnowledge Base Context:\n{context_str}"
            messages.append({"role": "user", "content": prompt})

            client = openai.AsyncOpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com",
            )
            response = await client.chat.completions.create(
                model="deepseek-chat", messages=messages
            )

            ai_message = response.choices[0].message.content
            return JSONResponse(
                {"status_code": 200, "status": "success", "reply": ai_message, "context": formatted_context}
            )
        except Exception as e:
            logger.error(f"KB Chat error: {e}\n{traceback.format_exc()}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @staticmethod
    async def ingest(request: Request):
        kb = _get_kb_instance()
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            form = await request.form()
            kb_id = form.get("kb_id")
            title = form.get("title") or "Document"
            file = form.get("file")
            text = form.get("text")
            url = form.get("url")

            if not kb_id:
                return JSONResponse({"error": "kb_id is required"}, status_code=400)

            if file and hasattr(file, "read"):
                file_bytes = await file.read()
                filename = getattr(file, "filename", "document.pdf")
                res = await ingest_file(kb, kb_id, filename, file_bytes)
                return JSONResponse({"status": "success", "result": res})
            elif url:
                res = await ingest_url(kb, kb_id, str(url))
                return JSONResponse({"status": "success", "result": res})
            elif text:
                res = await ingest_text(kb, kb_id, title, str(text))
                return JSONResponse({"status": "success", "result": res})
            return JSONResponse({"error": "No file, text or url provided"}, status_code=400)

        body = await request.json()
        kb_id = body.get("kb_id")
        title = body.get("title", "Document")
        text = body.get("text")
        url = body.get("url")

        if not kb_id:
            return JSONResponse({"error": "kb_id is required"}, status_code=400)

        if url:
            res = await ingest_url(kb, kb_id, url)
            return JSONResponse({"status": "success", "result": res})
        elif text:
            res = await ingest_text(kb, kb_id, title, text)
            return JSONResponse({"status": "success", "result": res})
        return JSONResponse({"error": "No text or url provided"}, status_code=400)

    @staticmethod
    async def backfill_embeddings(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}

        kb_id = body.get("kb_id") if isinstance(body, dict) else None
        limit = int(body.get("limit", 100)) if isinstance(body, dict) else 100

        kb = _get_kb_instance()
        updated = await kb.backfill_embeddings(kb_id=kb_id, limit=limit)
        return {"status": "success", "updated_chunks": updated}

    @staticmethod
    async def delete_document(request: Request):
        body = await request.json()
        kb_id = body.get("kb_id")
        title = body.get("title")

        if not kb_id or not title:
            return JSONResponse({"error": "kb_id and title are required"}, status_code=400)

        kb = _get_kb_instance()
        deleted = await kb.delete_document(kb_id, title)
        return {"status": "success", "deleted_chunks": deleted}

    @staticmethod
    async def upload_file(kb_id: str, file: UploadFile):
        kb = _get_kb_instance()
        file_bytes = await file.read()
        res = await ingest_file(kb, kb_id, file.filename, file_bytes)
        return {"status": "success", "result": res}

    @staticmethod
    async def ingest_text_endpoint(request: Request):
        body = await request.json()
        kb_id = body.get("kb_id")
        title = body.get("title", "Document")
        text = body.get("text", "")
        if not kb_id or not text:
            return JSONResponse({"error": "kb_id and text are required"}, status_code=400)

        kb = _get_kb_instance()
        res = await ingest_text(kb, kb_id, title, text)
        return {"status": "success", "result": res}

    @staticmethod
    async def ingest_url_endpoint(request: Request):
        body = await request.json()
        kb_id = body.get("kb_id")
        url = body.get("url")
        if not kb_id or not url:
            return JSONResponse({"error": "kb_id and url are required"}, status_code=400)

        kb = _get_kb_instance()
        res = await ingest_url(kb, kb_id, url)
        return {"status": "success", "result": res}

    @staticmethod
    async def list_knowledge(request: Request):
        kb_id = request.query_params.get("kb_id")
        conn = await get_db_connection()
        try:
            if kb_id:
                rows = await conn.fetch("SELECT id, kb_id, title, source_type, created_at FROM kb_pages WHERE kb_id = $1 ORDER BY created_at DESC", kb_id)
            else:
                rows = await conn.fetch("SELECT id, kb_id, title, source_type, created_at FROM kb_pages ORDER BY created_at DESC LIMIT 100")
            results = [dict(r) for r in rows]
            for r in results:
                if r.get("created_at"):
                    r["created_at"] = r["created_at"].isoformat()
            return {"status": "success", "count": len(results), "pages": results}
        finally:
            await conn.close()

    @staticmethod
    async def delete_page(page_id: str):
        conn = await get_db_connection()
        try:
            await conn.execute("DELETE FROM kb_pages WHERE id = $1", int(page_id))
            return {"status": "success", "message": f"Page {page_id} deleted"}
        finally:
            await conn.close()

    @staticmethod
    async def delete_by_kb(kb_id: str):
        conn = await get_db_connection()
        try:
            res = await conn.execute("DELETE FROM kb_pages WHERE kb_id = $1", kb_id)
            return {"status": "success", "message": f"Deleted pages for KB {kb_id}: {res}"}
        finally:
            await conn.close()


kb_controller = KBController()
