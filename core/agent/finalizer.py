"""Post-call finalization, LLM transcript analysis, S3 upload, and DB/webhook delivery."""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from helpers.s3 import upload_to_s3
from helpers.webhook import send_to_backend
from helpers.database import save_call_log_to_db, save_call_event
from helpers.telemetry import report_telemetry
from helpers.process_reconcile import reconcile_process_and_stage_id
from core.agent.pipeline_factory import build_post_call_llm
from core.agent.context_resolver import get_global_kb
from services.session_recorder import SessionRecorder

logger = logging.getLogger("mantra.agent")


def _as_int(val) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def normalize_datetime(dt_str: Optional[str]) -> Optional[str]:
    if not dt_str or not isinstance(dt_str, str):
        return None
    cleaned = dt_str.strip()
    if not cleaned or cleaned.lower() in ("null", "none"):
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(cleaned.split(".")[0].rstrip("Z"), fmt)
            return parsed.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    return cleaned


def format_e164_phone_number(number: str, country_code: str = "") -> str:
    cleaned = str(number or "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "").lstrip("+")
    if not cleaned:
        return ""
    if country_code:
        clean_cc = str(country_code).lstrip("+")
        if not cleaned.startswith(clean_cc):
            return f"+{clean_cc}{cleaned}"
    return f"+{cleaned}"


async def finalize_call(
    ctx,
    recorder: Optional[SessionRecorder],
    call_state: dict,
    effective_metadata: dict,
    fnc_ctx,
    history_snapshot: list,
):
    """Execute complete post-call lifecycle asynchronously with full diagnostics."""
    if call_state.get("_finalized"):
        logger.info("[DIAG] finalize(): Call already finalized — skipping duplicate execution")
        return
    call_state["_finalized"] = True

    post_call_llm = build_post_call_llm()
    recording_url = None
    transcript_data = None
    summary_text = None
    tos_sent = False
    duration = 0
    call_status = "Failed"
    next_call_on = None
    current_stage_id = None
    new_stage_id = None
    derived_process_id = None
    client_custom_fields = {}
    call_payload = {}
    webhook_payload = {}
    delivered = False

    async def _telemetry(msg: str, data: dict = None):
        tos_task_id = call_payload.get("metadata", {}).get("tos_task_id") or call_payload.get("tos_task_id")
        if tos_task_id:
            await report_telemetry(
                tos_task_id=tos_task_id,
                message=msg,
                call_id=str(call_payload.get("call_id") or (ctx.job.id if ctx.job else "")),
                level="INFO",
                data=data,
            )

    try:
        logger.info("[DIAG] finalize(): Starting post-call processing...")
        if "timeline" in call_state:
            call_state["timeline"].append({
                "event": "Call Finalization Started",
                "timestamp": datetime.now(tz=timezone.utc).isoformat() + "Z",
            })
        await _telemetry("Post-call processing started")

        # 1. Pre-load call metadata
        logger.info("[DIAG] finalize(): Step 1 — Loading call metadata...")
        try:
            if effective_metadata:
                call_payload = dict(effective_metadata)
                logger.info(f"[DIAG] finalize(): Using _effective_call_metadata with {len(call_payload)} keys")
            else:
                raw_meta = ctx.job.metadata if (ctx.job and ctx.job.metadata) else "{}"
                call_payload = json.loads(raw_meta) if raw_meta else {}
                logger.info(f"[DIAG] finalize(): Parsed raw job metadata with {len(call_payload)} keys")
        except Exception as e:
            logger.error(f"[DIAG] finalize(): Failed to parse call metadata: {e}")

        # For inbound calls, store KB tracked process_id and stage_id hints
        if call_payload.get("direction") == "inbound":
            try:
                if fnc_ctx and hasattr(fnc_ctx, "used_kb_process_ids"):
                    used_pids = fnc_ctx.used_kb_process_ids
                    if used_pids:
                        call_payload["kb_tracked_process_id"] = used_pids[0]
                        logger.info(f"KB-tracked process_id hint for inbound: {used_pids[0]}")
                if fnc_ctx and hasattr(fnc_ctx, "used_kb_stage_ids"):
                    used_sids = fnc_ctx.used_kb_stage_ids
                    if used_sids:
                        call_payload["kb_tracked_stage_id"] = used_sids[0]
                        logger.info(f"KB-tracked stage_id hint for inbound: {used_sids[0]}")
            except Exception as e:
                logger.error(f"Failed to extract KB usage metadata: {e}")

        # Determine call status based on whether user joined and spoke
        user_spoke = False
        for msg in history_snapshot:
            role = msg.role.name if hasattr(msg.role, "name") else str(msg.role)
            if role.lower() in ("user", "caller"):
                user_spoke = True
                break

        call_id = call_payload.get("call_id") or call_payload.get("voice_id") or (ctx.job.id if ctx.job else "")
        logger.info(f"[DIAG] finalize(): user_joined={call_state.get('user_joined')} user_spoke={user_spoke} history_size={len(history_snapshot)}")

        is_inbound = (call_payload.get("direction") == "inbound")
        is_user_joined = bool(call_state.get("user_joined") or is_inbound)

        if not is_user_joined:
            initiated_str = call_state.get("call_initiated_at") or (call_payload.get("metadata", {}) or {}).get("call_initiated_at")
            ring_time = 0
            if initiated_str:
                try:
                    initiated = datetime.strptime(initiated_str, "%Y-%m-%dT%H:%M:%S")
                    ring_time = (datetime.now() - initiated).total_seconds()
                except (ValueError, TypeError):
                    pass
            logger.info(f"[DIAG] finalize(): ring_time={ring_time:.0f}s (from call_initiated_at={initiated_str})")
            if ring_time >= 30:
                call_status = "No Answer"
            elif ring_time >= 3:
                call_status = "Busy"
            else:
                call_status = "Failed"
        elif not user_spoke and not is_inbound:
            call_status = "No Answer"
        else:
            call_status = "Completed"
        logger.info(f"[DIAG] finalize(): call_status determined as '{call_status}' (is_inbound={is_inbound}, user_spoke={user_spoke})")

        # 2. Flush recording tasks and upload to S3 (bounded by 10s timeout)
        logger.info(f"[DIAG] finalize(): Step 2 — Stopping recording...")
        try:
            if recorder and hasattr(recorder, "stop_recording"):
                await recorder.stop_recording()
                track_count = len(getattr(recorder, "_tracks", []))
                logger.info(f"[DIAG] finalize(): Recording stopped. track_count={track_count}")
                mp3_bytes = recorder.get_combined_mp3_bytes()
                if mp3_bytes:
                    logger.info(f"[DIAG] finalize(): Got {len(mp3_bytes)} bytes of MP3 audio, uploading to S3...")
                    call_id_for_key = (
                        call_payload.get("call_id")
                        or call_payload.get("voice_id")
                        or (ctx.job.id if ctx.job else "unknown")
                    )
                    s3_key = f"recordings/{call_id_for_key}.mp3"
                    loop = asyncio.get_running_loop()
                    recording_url = await asyncio.wait_for(
                        loop.run_in_executor(None, upload_to_s3, mp3_bytes, s3_key),
                        timeout=10.0,
                    )
                    logger.info(f"[DIAG] finalize(): S3 recording: {'uploaded' if recording_url else 'upload failed'}")
                else:
                    logger.info("[DIAG] finalize(): No audio data captured for recording")
        except asyncio.TimeoutError:
            logger.warning("[DIAG] finalize(): S3 recording upload timed out after 10s — proceeding without recording_url")
        except Exception as e:
            logger.error(f"[DIAG] finalize(): Recording/S3 step failed: {e}", exc_info=True)

        # 3. Build transcript from captured history snapshot
        logger.info(f"[DIAG] finalize(): Step 3 — Building transcript from {len(history_snapshot)} messages...")
        try:
            transcript_data = SessionRecorder.build_transcript(list(history_snapshot))
            logger.info(f"[DIAG] finalize(): Transcript built ({len(history_snapshot)} messages, {len(transcript_data or '')} chars)")
        except Exception as e:
            logger.error(f"[DIAG] finalize(): Transcript step failed: {e}", exc_info=True)

        # 4. Calculate duration
        if recorder and hasattr(recorder, "recording_duration_seconds"):
            duration = int(recorder.recording_duration_seconds)

        # 5. Run unified analysis (bounded by 70s timeout)
        direction = call_payload.get("direction")
        if direction == "inbound":
            try:
                if fnc_ctx and hasattr(fnc_ctx, "used_kb_process_ids"):
                    used_pids = fnc_ctx.used_kb_process_ids
                    if used_pids and not call_payload.get("kb_tracked_process_id"):
                        call_payload["kb_tracked_process_id"] = used_pids[0]
                        logger.info(f"Using KB-tracked process_id hint for inbound before analysis: {used_pids[0]}")
                if fnc_ctx and hasattr(fnc_ctx, "used_kb_stage_ids"):
                    used_sids = fnc_ctx.used_kb_stage_ids
                    if used_sids and not call_payload.get("kb_tracked_stage_id"):
                        call_payload["kb_tracked_stage_id"] = used_sids[0]
                        logger.info(f"Using KB-tracked stage_id hint for inbound before analysis: {used_sids[0]}")
            except Exception as e:
                logger.error(f"Failed to extract KB usage metadata before analysis: {e}")

        current_stage_id = call_payload.get("stage_id") or call_payload.get("kb_tracked_stage_id")
        stage_details = call_payload.get("stageDetails", [])
        kb_process_stage_data = (
            fnc_ctx.used_process_stage_data 
            if (fnc_ctx and hasattr(fnc_ctx, 'used_process_stage_data') and fnc_ctx.used_process_stage_data) 
            else None
        )
        if not kb_process_stage_data and fnc_ctx and hasattr(fnc_ctx, 'kb_ids') and fnc_ctx.kb_ids:
            try:
                kb = get_global_kb()
                kb_process_stage_data = await kb.get_process_stage_data_for_kb_ids(fnc_ctx.kb_ids)
                if kb_process_stage_data:
                    logger.info(f"Loaded {len(kb_process_stage_data)} process_stage_data entries from DB for KB ids: {fnc_ctx.kb_ids}")
            except Exception as e:
                logger.error(f"Failed to fetch fallback KB process_stage_data from DB: {e}")

        summary_text = None
        new_stage_id = current_stage_id
        derived_process_id = None
        derived_user_intent = None
        client_custom_fields = call_payload.get("client_custom_fields", {})
        if not isinstance(client_custom_fields, dict):
            client_custom_fields = {}

        if call_status in ["Busy", "Incomplete", "No Answer"]:
            logger.info(f"[DIAG] finalize(): Call status is {call_status}. Skipping LLM analysis.")
            summary_text = f"Call failed with status: {call_status}. The user did not speak or answer."
            duration = 0
            not_answering_id = current_stage_id
            for stage in stage_details:
                desc = stage.get("description", "").lower()
                if any(k in desc for k in ("not answering", "failed", "incomplete", "busy")):
                    not_answering_id = stage.get("stage_id")
                    break
            new_stage_id = not_answering_id
        else:
            try:
                if post_call_llm and history_snapshot:
                    logger.info(f"[DIAG] finalize(): Step 5 — Running analyze_call with {len(list(history_snapshot))} messages...")
                    client_country_code = call_payload.get("client_country_code") or call_payload.get("country_code", "")

                    analysis = await asyncio.wait_for(
                        SessionRecorder.analyze_call(
                            llm_engine=post_call_llm,
                            history=list(history_snapshot),
                            current_stage_id=current_stage_id,
                            stage_details=stage_details,
                            duration=duration,
                            client_country_code=client_country_code,
                            process_stage_data=kb_process_stage_data,
                        ),
                        timeout=70.0,
                    )
                    summary_text = analysis.get("summary")
                    new_stage_id = analysis.get("new_stage_id")
                    derived_process_id = analysis.get("process_id")
                    derived_user_intent = analysis.get("user_intent")
                    extracted_client_name = analysis.get("client_name")

                    if extracted_client_name:
                        clean_name = str(extracted_client_name).strip()
                        if clean_name and clean_name.lower() not in ["user", "unknown", "n/a", "none", "null", ""]:
                            curr_name = str(call_payload.get("client_name") or "").strip()
                            if not curr_name or curr_name.lower() in ["user", "unknown", "n/a"]:
                                call_payload["client_name"] = clean_name
                                logger.info(f"[DIAG] finalize(): Extracted client_name from call analysis: {clean_name}")

                    if derived_process_id:
                        call_payload["process_id"] = derived_process_id
                    elif not call_payload.get("process_id") and call_payload.get("kb_tracked_process_id"):
                        call_payload["process_id"] = call_payload.get("kb_tracked_process_id")

                    next_call_on = normalize_datetime(analysis.get("next_call_on"))

                    if analysis.get("appointment_date_time"):
                        client_custom_fields["appointment_date_time"] = analysis["appointment_date_time"]
                    if analysis.get("doctor"):
                        client_custom_fields["doctor"] = analysis["doctor"]
                    if analysis.get("hospital_location"):
                        client_custom_fields["hospital_location"] = analysis["hospital_location"]

                    logger.info(
                        f"Analysis completed. Process: {derived_process_id}, New Stage ID: {new_stage_id}, "
                        f"Next Call On: {next_call_on}, User Intent: {derived_user_intent}, Client Name: {call_payload.get('client_name')}"
                    )
                else:
                    logger.warning("Skipping analysis: LLM or history unavailable after session close")
            except asyncio.TimeoutError:
                logger.warning("[DIAG] finalize(): analyze_call timed out — using fallback summary")
                summary_text = "Call completed. Summary timed out during processing."
            except Exception as e:
                logger.error(f"Analysis or summary generation failed: {e}", exc_info=True)

        if not summary_text or not str(summary_text).strip():
            if transcript_data and transcript_data.strip():
                summary_text = f"Call completed ({duration}s). Transcript snippet: {transcript_data[:180]}..."
            else:
                summary_text = "Call completed."

    except Exception as e:
        logger.error(f"[DIAG] finalize(): Pipeline error in finalize: {e}", exc_info=True)

    # 6. Build webhook payload — separate structures for inbound vs outbound
    resolved_call_id = call_payload.get("call_id") or call_payload.get("voice_id") or (ctx.job.id if ctx.job else "")

    kb_referred = bool(direction == "inbound" and (call_payload.get("process_id") or call_payload.get("stage_id") or call_payload.get("kb_tracked_process_id") or derived_process_id))
    if direction == "inbound":
        effective_process_id = _as_int(derived_process_id or call_payload.get("process_id") or call_payload.get("kb_tracked_process_id")) if kb_referred else None
    else:
        effective_process_id = _as_int(derived_process_id or call_payload.get("process_id") or call_payload.get("kb_tracked_process_id"))

    initial_stage_id = _as_int(current_stage_id if current_stage_id is not None else call_payload.get("stage_id") or call_payload.get("kb_tracked_stage_id"))
    analysis_stage_id = _as_int(new_stage_id) if new_stage_id is not None else None

    payload_stage_id = initial_stage_id
    payload_new_stage_id = analysis_stage_id if analysis_stage_id is not None else initial_stage_id

    # Reconcile effective_process_id and payload_new_stage_id against kb_process_stage_data
    if kb_process_stage_data:
        effective_process_id, payload_new_stage_id = reconcile_process_and_stage_id(
            process_id=effective_process_id,
            stage_id=payload_new_stage_id,
            process_stage_data=kb_process_stage_data,
        )

    if call_status not in ["No Answer", "Busy", "Failed"]:
        if initial_stage_id is not None and payload_new_stage_id != initial_stage_id:
            call_status = "Completed"
            logger.info(f"[DIAG] finalize(): Stage updated from {initial_stage_id} to {payload_new_stage_id} — call_status='Completed'")
        elif initial_stage_id is None and payload_new_stage_id is not None:
            call_status = "Completed"
            logger.info(f"[DIAG] finalize(): New stage assigned ({payload_new_stage_id}) with no initial stage — call_status='Completed'")
        else:
            call_status = "Incomplete"
            logger.info(f"[DIAG] finalize(): Stage not updated (new_stage_id={payload_new_stage_id}, initial={initial_stage_id}) — call_status='Incomplete'")

    if direction == "inbound":
        raw_caller_phone = call_state.get("caller_phone_number") or call_payload.get("client_phone_number") or call_payload.get("client_phone") or ""
        cc_code = call_payload.get("client_country_code") or call_payload.get("country_code") or ""
        formatted_caller_phone = format_e164_phone_number(raw_caller_phone, country_code=cc_code)

        webhook_payload = {
            "event": "CALL_DATA_INBOUND_UPDATE",
            "data": {
                "org_id": _as_int(call_payload.get("org_id")),
                "call_recording": recording_url or "",
                "process_id": effective_process_id,
                "stage_id": payload_stage_id,
                "new_stage_id": payload_new_stage_id,
                "call_status": call_status,
                "client_name": call_payload.get("client_name") or "",
                "client_email": call_payload.get("client_email") or "",
                "client_phone_number": formatted_caller_phone,
                "call_duration": duration,
                "call_transcript": transcript_data or "",
                "ai_summary": summary_text or "",
                "next_call_on": normalize_datetime(next_call_on) or "",
                "called_on": call_state.get("call_initiated_at") or call_state.get("agent_joined_at") or "",
                "user_intent": derived_user_intent,
                "call_intent": derived_user_intent,
                "meta_data": {
                    "document_id": str(call_payload.get("call_id") or call_payload.get("voice_id") or (ctx.job.id if ctx.job else "")),
                    "provider": (call_payload.get("metadata", {}) or {}).get("provider", ""),
                },
            },
        }
    else:
        event_name = "CALL_RETRY" if call_status in ["No Answer", "Busy", "Failed"] else "CALL_DATA_UPDATE"
        if event_name == "CALL_RETRY":
            webhook_payload = {
                "event": event_name,
                "data": {
                    "call_id": resolved_call_id,
                    "called_on": call_state.get("call_initiated_at"),
                    "call_status": call_status,
                    "ai_call_id": ctx.job.id if ctx.job else "",
                },
            }
        else:
            webhook_payload = {
                "event": event_name,
                "data": {
                    "client_id": call_payload.get("lead_id"),
                    "call_id": resolved_call_id,
                    "call_status": call_status,
                    "call_transcript": transcript_data,
                    "ai_summary": summary_text,
                    "recording_url": recording_url,
                    "call_duration_seconds": duration,
                    "next_call_on": normalize_datetime(next_call_on) or "",
                    "called_on": call_state.get("call_initiated_at") or call_state.get("agent_joined_at") or None,
                    "ai_call_id": ctx.job.id if ctx.job else "",
                    "process_id": effective_process_id,
                    "stage_id": payload_stage_id,
                    "new_stage_id": payload_new_stage_id,
                    "user_intent": derived_user_intent,
                    "call_intent": derived_user_intent,
                    "metadata": call_payload.get("metadata", {}),
                    "client_custom_fields": client_custom_fields or {},
                    "call_custom_fields": call_payload.get("call_custom_fields", {}),
                },
            }

    # 8. Send to MantraAssist backend and save to local DB
    logger.info(f"[DIAG] finalize(): Step 8 — Saving to DB and delivering webhook...")
    c_id = webhook_payload.get("data", {}).get("call_id", (ctx.job.id if ctx.job else ""))
    try:
        caller_number = call_payload.get("call_from") or call_payload.get("caller_number") or call_state.get("caller_phone_number") or ""
        called_number = call_payload.get("client_phone") or call_payload.get("client_phone_number") or call_payload.get("called_number") or ""
        call_trunk_id = call_payload.get("call_from_id") or call_payload.get("trunk_id") or ""
        await save_call_log_to_db(
            call_id=str(c_id),
            call_log=json.dumps(webhook_payload.get("data", {}), indent=2),
            status=call_status,
            recording_url=recording_url,
            caller_number=caller_number,
            called_number=called_number,
            trunk_id=call_trunk_id,
        )
        logger.info(f"[DIAG] finalize(): Call log saved to DB for call_id={c_id}")
    except Exception as db_err:
        logger.error(f"[DIAG] finalize(): Error calling save_call_log_to_db: {db_err}")

    logger.info("[DIAG] finalize(): Queueing webhook to UI Server via Redis...")
    try:
        import redis.asyncio as redis
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            client = redis.from_url(redis_url, decode_responses=True)
            await client.rpush("mantra:pending_webhooks", json.dumps(webhook_payload))
            await client.aclose()
            delivered = True
            logger.info(f"[DIAG] finalize(): Webhook queued to UI Server successfully (call_id={c_id})")
        else:
            logger.warning("[DIAG] finalize(): REDIS_URL not set. Falling back to synchronous HTTP delivery.")
            delivered = await send_to_backend(webhook_payload)
    except Exception as e:
        logger.error(f"[DIAG] finalize(): Redis queueing failed, falling back to HTTP: {e}")
        delivered = await send_to_backend(webhook_payload)

    tos_sent = True
    await _telemetry(f"data_sent_to_backend — status={call_status}, queued_to_redis={'yes' if delivered else 'no'}")

    # Log backend delivery event to audit trail
    backend_cid = resolved_call_id or (ctx.job.id if ctx.job else "")
    try:
        await save_call_event(
            call_id=str(backend_cid),
            event_type="backend_sent" if delivered else "backend_failed",
            event_source="agent",
            event_payload={k: v for k, v in webhook_payload.items() if k != "prompt"},
            event_status="success" if delivered else "failed",
            event_log=f"status={call_status} duration={duration}s {'delivered' if delivered else 'failed'}",
        )
    except Exception as ev_err:
        logger.warning(f"Error saving backend call event: {ev_err}")

    await _telemetry(f"call_complete — status={call_status}, duration={duration}s")

    # Clear Redis call lock
    try:
        redis_url = os.getenv("REDIS_URL")
        if redis_url and c_id:
            import redis.asyncio as redis
            r_client = redis.from_url(redis_url, decode_responses=True)
            await r_client.delete(f"lock:call:{c_id}")
            await r_client.aclose()
            logger.info(f"[DIAG] finalize(): Cleared lock:call:{c_id}")
    except Exception as lock_err:
        logger.warning(f"[DIAG] finalize(): Failed to clear call lock: {lock_err}")

    logger.info(
        f"[DIAG] ======== POST-CALL COMPLETE ========\n"
        f"  Call ID: {ctx.job.id if ctx.job else 'N/A'}\n"
        f"  Lead: {webhook_payload.get('data', {}).get('client_id', 'N/A')}\n"
        f"  Status: {webhook_payload.get('data', {}).get('call_status', 'N/A')}\n"
        f"  Duration: {duration}s\n"
        f"  S3: {'✓' if recording_url else '✗'}\n"
        f"  Backend: {'✓' if delivered else '✗'}\n"
        f"  TOS: {'✓' if tos_sent else '✗'}\n"
        f"  Transcript length: {len(transcript_data or '')} chars\n"
        f"  Summary: {summary_text[:200] if summary_text else 'None'}"
    )
