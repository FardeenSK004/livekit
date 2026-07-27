"""Agent function tools with injected session context."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Optional

from livekit.agents import Agent, AgentSession, JobContext, llm

from app.agent.tools.end_call import execute_end_call
from app.agent.tools.handoff import execute_handoff
from app.agent.tools.search_kb import execute_search
from app.kb.retriever import KnowledgeRetriever
from app.services.telemetry import report_telemetry

logger = logging.getLogger("app.agent.tools")


class AssistantFunctions:
    """LiveKit function tools bound to a single call session."""

    def __init__(
        self,
        job_metadata: str,
        room_name: str,
        ctx: JobContext | None = None,
        kb_ids: list[str] | None = None,
        kb_tags: list[str] | None = None,
        create_bg_task=None,
        force_disconnect=None,
    ):
        self.job_metadata = job_metadata
        self.room_name = room_name
        self.handoff_triggered = False
        self.agent: Agent | None = None
        self.session: AgentSession | None = None
        self.ctx = ctx
        self.kb_ids = kb_ids or []
        self.kb_tags = kb_tags or []
        self._retriever: KnowledgeRetriever | None = None
        self._create_bg_task = create_bg_task
        self._force_disconnect = force_disconnect
        self._disconnect_task = None
        self.call_id = None
        self.tos_task_id = None
        if job_metadata:
            try:
                payload = json.loads(job_metadata)
                self.call_id = str(payload.get("call_id") or payload.get("voice_id") or "")
                self.tos_task_id = payload.get("tos_task_id") or payload.get("metadata", {}).get("tos_task_id")
            except Exception:
                pass

    def _telemetry(self, message: str, call_id: str | None = None, data: dict | None = None):
        if self.tos_task_id:
            cid = call_id or self.call_id or ""
            self._create_bg_task(
                report_telemetry(
                    tos_task_id=self.tos_task_id,
                    message=f"[Agent Worker] {message}",
                    call_id=cid,
                    data=data,
                )
            )

    async def _get_retriever(self) -> KnowledgeRetriever:
        if self._retriever is None:
            self._retriever = KnowledgeRetriever()
        return self._retriever

    @llm.function_tool(
        description=(
            "Transfer the call to a human agent in a specific department when the user requests it, "
            "you cannot resolve their issue, or they seem frustrated. "
            "Specify the department (e.g., 'refund', 'support', 'billing', 'general') "
            "based on what the user needs."
        )
    )
    async def transfer_to_human(
        self,
        reason: Annotated[
            str, "Why the human agent is needed — be specific about the user's request"
        ],
        department: Annotated[
            str,
            "The department to transfer to (e.g., refund, support, billing, general)",
        ] = "general",
    ):
        if self.handoff_triggered:
            logger.warning("Handoff already in progress — ignoring duplicate request")
            return "TRANSFER_ALREADY_IN_PROGRESS."

        self.handoff_triggered = True
        self.last_reason = reason
        self.last_department = department

        return await execute_handoff(
            reason=reason,
            department=department,
            room_name=self.room_name,
            job_metadata=self.job_metadata,
            agent=self.agent,
            session=self.session,
        )

    @llm.function_tool(
        description=(
            "Search the knowledge base for factual information relevant to the user's question. "
            "Use this tool to retrieve accurate information about products, services, policies, "
            "procedures, pricing, locations, schedules, people, organizations, documents, "
            "regulations, FAQs, or any domain-specific content stored in the knowledge base. "
            "ALWAYS use this tool before answering questions that require factual or "
            "organization-specific information. If the user switches topics to a specific category "
            "(like 'support' or 'pricing'), you can provide that category in 'specific_tag' "
            "to override the default search scope."
        )
    )
    async def search_knowledge_base(
        self,
        query: Annotated[
            str,
            "The search query to look up in the knowledge base. Be specific.",
        ],
        specific_tag: Annotated[
            Optional[str],
            "An optional specific tag or category to search within.",
        ] = None,
    ):
        retriever = await self._get_retriever()
        return await execute_search(
            query,
            kb_ids=self.kb_ids,
            kb_tags=self.kb_tags,
            specific_tag=specific_tag,
            retriever=retriever,
        )

    @llm.function_tool(
        description=(
            "End the call. Call this tool when the conversation is over — the user said goodbye, "
            "is not interested, or there is nothing left to discuss."
        )
    )
    async def end_call(self):
        self._telemetry("Call ended by agent")
        return await execute_end_call(
            session=self.session,
            ctx=self.ctx,
            force_disconnect=self._force_disconnect,
            create_bg_task=self._create_bg_task,
        )


def get_agent_tools(fnc_ctx: AssistantFunctions):
    """Return base tool callables for Agent registration."""
    return [
        fnc_ctx.end_call,
        fnc_ctx.search_knowledge_base,
        fnc_ctx.transfer_to_human,
    ]


__all__ = [
    "AssistantFunctions",
    "get_agent_tools",
]
