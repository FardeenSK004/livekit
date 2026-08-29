"""Post-call finalization, LLM transcript analysis, S3 upload, and DB/webhook delivery."""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from helpers.s3 import upload_to_s3
from helpers.webhook import send_to_backend
from helpers.database import save_call_log_to_db
from helpers.telemetry import report_telemetry
from helpers.process_reconcile import reconcile_process_and_stage_id
from core.agent.pipeline_factory import build_post_call_llm
from services.session_recorder import SessionRecorder

logger = logging.getLogger("core.agent.finalizer")


async def finalize_call(
    ctx,
    recorder: Optional[SessionRecorder],
    call_state: dict,
    effective_metadata: dict,
    fnc_ctx,
    history_snapshot: list,
):
    """Execute complete post-call lifecycle asynchronously."""
    if call_state.get("_finalized"):
        return
    call_state["_finalized"] = True

    post_call_llm = build_post_call_llm()
    recording_url = None
    call_payload = dict(effective_metadata or {})
    call_id = str(call_payload.get("call_id") or call_payload.get("voice_id") or (ctx.job.id if ctx.job else ""))

    # 1. Determine status
    user_spoke = any(
        (getattr(m.role, "name", str(m.role)).lower() in ["user", "caller"])
        for m in history_snapshot
    )
    is_inbound = call_payload.get("direction") == "inbound"
    is_user_joined = bool(call_state.get("user_joined") or is_inbound)

    if not is_user_joined:
        call_status = "No Answer"
    elif not user_spoke and not is_inbound:
        call_status = "No Answer"
    else:
        call_status = "Completed"

    # 2. Recording S3 upload
    duration = 0
    try:
        if recorder and hasattr(recorder, "stop_recording"):
            await recorder.stop_recording()
            duration = int(getattr(recorder, "recording_duration_seconds", 0))
            mp3_bytes = recorder.get_combined_mp3_bytes()
            if mp3_bytes:
                s3_key = f"recordings/{call_id}.mp3"
                loop = asyncio.get_running_loop()
                recording_url = await asyncio.wait_for(
                    loop.run_in_executor(None, upload_to_s3, mp3_bytes, s3_key),
                    timeout=10.0,
                )
    except Exception as e:
        logger.error(f"Failed to upload recording to S3: {e}")

    # 3. Post-call LLM analysis
    analysis_result = {}
    current_stage_id = call_payload.get("stage_id")
    stage_details = call_payload.get("stageDetails") or call_payload.get("stage_details") or []
    client_country_code = call_payload.get("client_country_code") or call_payload.get("country_code", "")
    kb_process_stage_data = call_payload.get("process_stage_data") or []

    if history_snapshot:
        try:
            analysis_result = await SessionRecorder.analyze_call(
                llm_engine=post_call_llm,
                history=list(history_snapshot),
                current_stage_id=current_stage_id,
                stage_details=stage_details,
                duration=duration,
                client_country_code=client_country_code,
                process_stage_data=kb_process_stage_data,
            )
        except Exception as e:
            logger.error(f"Post-call LLM analysis failed: {e}")

    summary_text = analysis_result.get("summary") or "Call completed."
    transcript_text = SessionRecorder.build_transcript(list(history_snapshot))

    # 4. Save to Database
    call_log_data = {
        "call_id": call_id,
        "status": call_status,
        "recording_url": recording_url,
        "caller_number": call_payload.get("client_phone") or call_payload.get("phone", ""),
        "called_number": call_payload.get("call_from", ""),
        "trunk_id": call_payload.get("trunk_id", ""),
        "call_log": {
            "ai_summary": summary_text,
            "transcript": transcript_text,
            "sentiment_score": analysis_result.get("sentiment_score"),
            "call_duration_seconds": duration,
        },
    }
    await save_call_log_to_db(call_log_data)

    # 5. Dispatch Webhook to Backend
    webhook_body = {
        "event": "CALL_COMPLETED",
        "call_id": call_id,
        "status": call_status,
        "recording_url": recording_url,
        "summary": summary_text,
        "transcript": transcript_text,
        "analysis": analysis_result,
        "payload": call_payload,
    }
    await send_to_backend(webhook_body)
    logger.info(f"Finalized call {call_id} with status {call_status}")
