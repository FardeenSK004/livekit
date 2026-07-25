"""Post-call finalization — recording, analysis, webhook, DB, Redis."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any, Optional

import asyncpg
import redis.asyncio as redis

from app.config import settings
from app.recording.session_recorder import SessionRecorder
from app.services.datetime_utils import normalize_to_iso8601
from app.services.s3 import s3_service
from app.services.webhook import webhook_service

logger = logging.getLogger("app.agent.finalize")


async def finalize_call(
    *,
    ctx,
    call_state: dict,
    history_snapshot: list,
    recorder: SessionRecorder,
    llm_engine,
    effective_call_metadata: dict,
    entrypoint_start_time: float,
) -> None:
    """Run the full post-call pipeline (shielded from cancellation)."""
    recording_url = ""
    transcript_data = ""
    summary_text = ""
    duration = 0
    call_status = "Error"
    webhook_payload = None
    call_payload: dict[str, Any] = {}
    delivered = False

    try:
        logger.info("Starting post-call processing...")
        if "timeline" in call_state:
            call_state["timeline"].append(
                {
                    "event": "Call Finalization Started",
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                }
            )

        try:
            if effective_call_metadata:
                call_payload = dict(effective_call_metadata)
            else:
                call_payload = (
                    json.loads(ctx.job.metadata) if ctx.job.metadata else {}
                )
        except Exception as e:
            logger.error("Failed to parse call metadata: %s", e)
            call_payload = {}

        user_spoke = False
        for msg in history_snapshot:
            role = msg.role.name if hasattr(msg.role, "name") else str(msg.role)
            if role.lower() == "user":
                user_spoke = True
                break

        call_id = (
            call_payload.get("call_id")
            or call_payload.get("voice_id")
            or ctx.job.id
        )

        redis_status = await _fetch_sip_error_status(str(call_id))
        call_status = _determine_call_status(
            redis_status=redis_status,
            user_joined=call_state.get("user_joined", False),
            user_spoke=user_spoke,
            entrypoint_start_time=entrypoint_start_time,
        )

        try:
            await recorder.stop_recording()
            if call_status == "Completed":
                mp3_bytes = recorder.get_combined_mp3_bytes()
                if mp3_bytes:
                    s3_key = f"recordings/{call_id}.mp3"
                    loop = asyncio.get_running_loop()
                    recording_url = (
                        await loop.run_in_executor(
                            None, _upload_recording_sync, mp3_bytes, s3_key
                        )
                        or ""
                    )
                    logger.info(
                        "S3 recording: %s",
                        "uploaded" if recording_url else "upload failed",
                    )
                else:
                    logger.info("No audio data captured for recording")
            else:
                logger.info(
                    "Skipping recording upload because call_status is %s",
                    call_status,
                )
        except Exception as e:
            logger.error("Recording/S3 step failed: %s", e, exc_info=True)

        try:
            transcript_data = SessionRecorder.build_transcript(list(history_snapshot))
            logger.info("Transcript built (%s messages)", len(history_snapshot))
        except Exception as e:
            logger.error("Transcript step failed: %s", e, exc_info=True)

        if hasattr(recorder, "recording_duration_seconds"):
            duration = int(recorder.recording_duration_seconds)
        else:
            duration = 0

        current_stage_id = call_payload.get("stage_id")
        stage_details = call_payload.get("stageDetails", [])
        new_stage_id = current_stage_id
        next_call_on = None
        client_custom_fields = call_payload.get("client_custom_fields", {})
        if not isinstance(client_custom_fields, dict):
            client_custom_fields = {}

        if call_status in ["Busy", "Incomplete", "No Answer"]:
            logger.info(
                "Call status is %s. Skipping LLM analysis and applying 'Not Answering' logic.",
                call_status,
            )
            summary_text = (
                f"Call failed with status: {call_status}. "
                "The user did not speak or answer."
            )
            duration = 0
            not_answering_id = current_stage_id
            for stage in stage_details:
                desc = stage.get("description", "").lower()
                if (
                    "not answering" in desc
                    or "failed" in desc
                    or "incomplete" in desc
                    or "busy" in desc
                ):
                    not_answering_id = stage.get("stage_id")
                    break
            new_stage_id = not_answering_id

            current_time = datetime.datetime.now()
            tomorrow = current_time + datetime.timedelta(hours=24)
            next_call_on = tomorrow.strftime("%Y-%m-%d %H:%M:%S")
        else:
            try:
                if llm_engine and history_snapshot:
                    client_country_code = call_payload.get(
                        "client_country_code"
                    ) or call_payload.get("country_code", "")

                    analysis = await SessionRecorder.analyze_call(
                        llm_engine=llm_engine,
                        history=list(history_snapshot),
                        current_stage_id=current_stage_id,
                        stage_details=stage_details,
                        duration=duration,
                        client_country_code=client_country_code,
                    )
                    summary_text = analysis["summary"]
                    new_stage_id = analysis["new_stage_id"]
                    next_call_on = analysis["next_call_on"]

                    if analysis.get("appointment_date_time"):
                        client_custom_fields["appointment_date_time"] = analysis[
                            "appointment_date_time"
                        ]
                    if analysis.get("doctor"):
                        client_custom_fields["doctor"] = analysis["doctor"]
                    if analysis.get("hospital_location"):
                        client_custom_fields["hospital_location"] = analysis[
                            "hospital_location"
                        ]

                    logger.info(
                        "Analysis completed. New Stage ID: %s, Next Call On: %s",
                        new_stage_id,
                        next_call_on,
                    )
                else:
                    logger.warning(
                        "Skipping analysis: LLM or history unavailable after session close"
                    )
            except Exception as e:
                logger.error(
                    "Analysis or summary generation failed: %s", e, exc_info=True
                )

        direction = call_payload.get("direction", "outbound")
        logger.info(
            "Building webhook payload: direction=%s, call_status=%s, call_id=%s",
            direction,
            call_status,
            call_payload.get("call_id"),
        )
        webhook_payload = {
            "event": "CALL_DATA_UPDATE",
            "data": {
                "client_id": call_payload.get("lead_id"),
                "call_id": call_payload.get("call_id")
                or call_payload.get("voice_id"),
                "call_status": call_status,
                "status": call_status,
                "direction": direction,
                "call_transcript": transcript_data,
                "ai_summary": summary_text,
                "summary": summary_text,
                "recording_url": recording_url,
                "call_duration_seconds": duration,
                "next_call_on": normalize_to_iso8601(next_call_on),
                "ai_call_id": ctx.job.id,
                "new_stage_id": new_stage_id,
                "process_id": call_payload.get("process_id"),
                "notes": "",
                "metadata": call_payload.get("metadata", {}),
                "client_custom_fields": client_custom_fields,
                "call_custom_fields": call_payload.get("call_custom_fields", {}),
                "client_phone": call_payload.get("client_phone")
                or call_payload.get("phone"),
                "trunk_id": call_payload.get("trunk_id"),
                "url": "",
                "timeline": call_state.get("timeline", []),
            },
        }

        if direction == "inbound":
            try:
                inbound_context = {
                    "org_id": call_payload.get("org_id"),
                    "kb_id": call_payload.get("kb_id"),
                    "phone_number": call_payload.get("phone_number"),
                    "provider": call_payload.get("provider"),
                }
                inbound_context = {
                    k: v for k, v in inbound_context.items() if v is not None
                }
                if inbound_context:
                    webhook_payload["data"]["inbound_context"] = inbound_context
                    webhook_payload["data"].update(inbound_context)
                    logger.info(
                        "Inbound webhook: added inbound_context=%s",
                        inbound_context,
                    )
                else:
                    logger.info("Inbound webhook: no inbound context to add")
            except Exception as ctx_err:
                logger.error(
                    "Failed to add inbound_context to webhook (non-fatal): %s",
                    ctx_err,
                )

    except Exception as e:
        logger.error("Pipeline error in finalize: %s", e, exc_info=True)

    try:
        if webhook_payload is None:
            webhook_payload = {
                "event": "CALL_DATA_UPDATE",
                "data": {
                    "ai_call_id": ctx.job.id,
                    "call_status": "Error",
                    "status": "Error",
                    "notes": "Post-call pipeline encountered an error — minimal payload sent",
                },
            }

        try:
            c_id = webhook_payload.get("data", {}).get("call_id", ctx.job.id)
            await _save_call_log_to_db(
                call_id=str(c_id),
                call_log=json.dumps(webhook_payload.get("data", {}), indent=2),
                status=call_status,
                recording_url=recording_url,
            )
        except Exception as db_err:
            logger.error("Error calling save_call_log_to_db: %s", db_err)

        logger.info("Delivering post-call webhook to backend...")
        logger.info("Webhook Payload:\n%s", json.dumps(webhook_payload))
        delivered = await webhook_service.send(webhook_payload)
    except Exception as e:
        logger.error("Webhook delivery failed: %s", e, exc_info=True)
        delivered = False

    try:
        call_id = call_payload.get("call_id")
        if call_id:
            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await r.hdel("calls:active", call_id)
            await r.set(f"calls:status:{call_id}", "completed")
            await r.aclose()
            logger.info("Freed capacity slot for call %s in Redis", call_id)
    except Exception as e:
        logger.error("Failed to free Redis capacity slot: %s", e)

    logger.info(
        "Post-call processing complete | Call ID: %s | Lead: %s | Status: %s | "
        "Duration: %ss | S3: %s | Backend: %s",
        ctx.job.id,
        webhook_payload.get("data", {}).get("client_id", "N/A"),
        webhook_payload.get("data", {}).get("call_status", "N/A"),
        duration,
        "yes" if recording_url else "no",
        "yes" if delivered else "no",
    )


def _determine_call_status(
    *,
    redis_status: Optional[str],
    user_joined: bool,
    user_spoke: bool,
    entrypoint_start_time: float,
) -> str:
    if redis_status:
        return redis_status
    if not user_joined:
        elapsed_time = asyncio.get_event_loop().time() - entrypoint_start_time
        if elapsed_time >= 25.0:
            return "No Answer"
        return "Busy"
    if not user_spoke:
        return "No Answer"
    return "Completed"


async def _fetch_sip_error_status(call_id: str) -> Optional[str]:
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        status = await r.get(f"sip_error_status:{call_id}")
        await r.aclose()
        return status
    except Exception as redis_err:
        logger.error("Failed to fetch precise SIP status from Redis: %s", redis_err)
        return None


def _upload_recording_sync(mp3_bytes: bytes, s3_key: str) -> Optional[str]:
    return s3_service.upload_bytes(mp3_bytes, s3_key)


async def _save_call_log_to_db(
    call_id: str, call_log: str, status: str, recording_url: str
) -> None:
    conn = None
    try:
        conn = await asyncpg.connect(settings.postgres_dsn, timeout=5.0)
        query = """
        INSERT INTO call_logs (call_id, call_log, status, recording_url)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (call_id) DO UPDATE
        SET call_log = EXCLUDED.call_log,
            status = EXCLUDED.status,
            recording_url = EXCLUDED.recording_url;
        """
        await conn.execute(query, call_id, call_log, status, recording_url)
        logger.info("Successfully saved call log to DB for call_id: %s", call_id)
    except Exception as e:
        logger.error("Failed to save call log to DB: %s", e)
    finally:
        if conn:
            await conn.close()
