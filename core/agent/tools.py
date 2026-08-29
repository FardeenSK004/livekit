"""Agent tools and AssistantFunctions tool definitions."""

import os
import json
import logging
import asyncio
from typing import Optional, List, Annotated
from livekit.agents import JobContext, llm

from core.kb.retriever import KnowledgeRetriever
from core.kb.knowledge_base import PostgresKnowledgeBase
from core.agent.context_resolver import get_global_kb
from helpers.telemetry import report_telemetry

logger = logging.getLogger("core.agent.tools")


class AssistantFunctions:
    """LiveKit agent callable toolset."""

    def __init__(
        self,
        job_metadata: str,
        room_name: str,
        ctx: Optional[JobContext] = None,
        kb_ids: Optional[List[str]] = None,
        kb_tags: Optional[List[str]] = None,
        call_state: Optional[dict] = None,
    ):
        self.job_metadata = job_metadata
        self.room_name = room_name
        self.handoff_triggered = False
        self._end_call_triggered = False
        self.call_state = call_state or {}
        self.agent = None
        self.session = None
        self.ctx = ctx
        self.call_id = None
        self.tos_task_id = None
        self.kb_ids = kb_ids or []
        self.kb_tags = kb_tags or []
        self._retriever: Optional[KnowledgeRetriever] = None

        if job_metadata:
            try:
                payload = json.loads(job_metadata)
                self.call_id = str(payload.get("call_id") or payload.get("voice_id") or "")
                self.tos_task_id = payload.get("tos_task_id") or payload.get("metadata", {}).get("tos_task_id")
            except Exception:
                pass

    def _telemetry(self, message: str, call_id: Optional[str] = None, data: Optional[dict] = None):
        if self.tos_task_id:
            cid = call_id or self.call_id or ""
            asyncio.create_task(
                report_telemetry(
                    tos_task_id=self.tos_task_id,
                    message=f"[Agent Worker] {message}",
                    call_id=cid,
                    data=data,
                )
            )

    async def _get_kb(self) -> PostgresKnowledgeBase:
        return get_global_kb()

    async def _get_retriever(self) -> KnowledgeRetriever:
        if self._retriever is None:
            kb = await self._get_kb()
            self._retriever = KnowledgeRetriever(kb)
        return self._retriever

    async def warmup(self):
        try:
            retriever = await self._get_retriever()
            await retriever.prefetch(self.kb_ids)
        except Exception as e:
            logger.warning(f"[KB] AssistantFunctions warmup error: {e}")

    @property
    def used_kb_process_ids(self) -> list[str]:
        if self._retriever is None:
            return []
        seen = set()
        result = []
        for meta in self._retriever.accessed_pages_meta:
            raw = meta.get("process_id")
            if isinstance(raw, list):
                for pid in raw:
                    if pid is not None and str(pid) not in seen:
                        seen.add(str(pid))
                        result.append(str(pid))
            elif raw is not None and str(raw) not in seen:
                seen.add(str(raw))
                result.append(str(raw))
        return result

    @property
    def used_kb_stage_ids(self) -> list[str]:
        if self._retriever is None:
            return []
        seen = set()
        result = []
        for meta in self._retriever.accessed_pages_meta:
            raw = meta.get("stage_id")
            if isinstance(raw, list):
                for sid in raw:
                    if sid is not None and str(sid) not in seen:
                        seen.add(str(sid))
                        result.append(str(sid))
            elif raw is not None and str(raw) not in seen:
                seen.add(str(raw))
                result.append(str(raw))
        return result

    @property
    def used_process_stage_data(self) -> list:
        if self._retriever is None:
            return []
        seen_ids = set()
        result = []
        for meta in self._retriever.accessed_pages_meta:
            psd = meta.get("process_stage_data")
            if isinstance(psd, list):
                for entry in psd:
                    pid = entry.get("id")
                    if pid is not None and pid not in seen_ids:
                        seen_ids.add(pid)
                        result.append(entry)
        return result

    @llm.function_tool(
        description=(
            "Search the knowledge base for factual information, doctor profiles, availability, working hours, pricing, services, "
            "policies, and any entity or topic asked by the caller. Call this tool silently without saying search fillers. "
            "Speak the retrieved answer directly."
        )
    )
    async def search_knowledge_base(
        self,
        query: Annotated[str, "The search query to look up in the knowledge base."],
        specific_tag: Annotated[Optional[str], "Optional specific category tag to filter."] = None,
    ):
        tags_to_search = [specific_tag] if specific_tag else self.kb_tags
        logger.info(f"Agent requested KB search: '{query}' with tags {tags_to_search}")
        retriever = await self._get_retriever()
        return await retriever.retrieve(query, kb_ids=self.kb_ids, tags=tags_to_search if tags_to_search else None)

    @llm.function_tool(
        description="End the call. Call this tool ONLY when the conversation has reached its final conclusion."
    )
    async def end_call(self):
        if self.call_state and not self.call_state.get("user_has_spoken", False) and not self.call_state.get("initial_greeting_done", False):
            logger.warning("end_call invoked before conversation started. Ignoring.")
            return "Call cannot be ended before conversation starts."

        logger.info("Agent decided to end call via function tool.")
        self._telemetry("Call ended by agent")
        self._end_call_triggered = True

        async def graceful_disconnect():
            await asyncio.sleep(3.0)
            if self.ctx and self.ctx.room:
                await self.ctx.room.disconnect()

        asyncio.create_task(graceful_disconnect())
        return ""
