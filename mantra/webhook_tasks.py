import os
import json
import asyncio
import logging
from typing import Dict, Any, List

from celery import Celery
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")

logger = logging.getLogger("mantra.webhook_tasks")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "mantra_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "mantra.webhook_tasks.process_postcall": {"queue": "webhook_processing"},
        "mantra.webhook_tasks.deliver_postcall": {"queue": "webhook_delivery"},
    }
)


def _run_async(coro):
    """Utility to run an async coroutine inside a synchronous Celery task worker."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # In case loop is already running in worker thread
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    else:
        return loop.run_until_complete(coro)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=2,
    name="mantra.webhook_tasks.process_postcall"
)
def process_postcall(self, event_id: str, postcall_data: Dict[str, Any]):
    """
    Worker Task (webhook_processing queue):
    1. Runs LLM analysis on transcript (or applies fallback for failed calls)
    2. Constructs final CALL_DATA_UPDATE payload
    3. Updates database audit log
    4. Enqueues deliver_postcall task
    """
    from mantra.utils import update_webhook_event, SessionRecorder, normalize_to_iso8601
    from livekit.agents import llm
    from livekit.plugins import openai, google

    logger.info(f"Processing post-call task: event_id={event_id}, call_id={postcall_data.get('call_id')}")

    try:
        _run_async(update_webhook_event(event_id, status="processing", increment_attempts=True))

        call_payload = postcall_data.get("call_payload", {})
        call_status = postcall_data.get("call_status", "Failed")
        duration = postcall_data.get("duration", 0)
        transcript_data = postcall_data.get("transcript")
        recording_url = postcall_data.get("recording_url")
        job_id = postcall_data.get("job_id")
        call_state = postcall_data.get("call_state", {})
        history_list = postcall_data.get("history", [])

        current_stage_id = call_payload.get("stage_id")
        stage_details = call_payload.get("stageDetails", [])
        
        summary_text = None
        new_stage_id = current_stage_id
        next_call_on = None
        client_custom_fields = call_payload.get("client_custom_fields", {})
        if not isinstance(client_custom_fields, dict):
            client_custom_fields = {}

        if call_status in ["Busy", "Incomplete", "No Answer"]:
            logger.info(f"Call status is {call_status}. Applying 'Not Answering' fallback stage logic.")
            summary_text = f"Call failed with status: {call_status}. The user did not speak or answer."
            duration = 0
            not_answering_id = current_stage_id
            for stage in stage_details:
                desc = stage.get("description", "").lower()
                if "not answering" in desc or "failed" in desc or "incomplete" in desc or "busy" in desc:
                    not_answering_id = stage.get("stage_id")
                    break
            new_stage_id = not_answering_id
        else:
            # Re-create LLM Engine for analysis
            ai_p = call_payload.get("ai_payload", {})
            if not isinstance(ai_p, dict):
                ai_p = {}
            model_name = str(ai_p.get("ai_model") or call_payload.get("model") or "openai").lower()

            if model_name == "gemini":
                llm_engine = google.LLM(model="gemini-2.5-flash")
            elif model_name == "deepseek":
                deepseek_key = os.getenv("DEEPSEEK_API_KEY")
                if not deepseek_key:
                    llm_engine = openai.LLM(model="gpt-4o-mini")
                else:
                    llm_engine = openai.LLM(
                        model="deepseek-v4-flash",
                        api_key=deepseek_key,
                        base_url="https://api.deepseek.com"
                    )
            else:
                llm_engine = openai.LLM(model="gpt-4o-mini")

            # Convert JSON history items to ChatMessage objects for analyze_call
            chat_history = []
            for item in history_list:
                role = item.get("role", "user")
                content = item.get("content", "")
                chat_history.append(llm.ChatMessage(role=role, content=[content]))

            if chat_history:
                try:
                    analysis = _run_async(
                        SessionRecorder.analyze_call(
                            llm_engine=llm_engine,
                            history=chat_history,
                            current_stage_id=current_stage_id,
                            stage_details=stage_details,
                            duration=duration
                        )
                    )
                    summary_text = analysis.get("summary")
                    new_stage_id = analysis.get("new_stage_id")
                    next_call_on = analysis.get("next_call_on")
                    
                    if analysis.get("appointment_date_time"):
                        client_custom_fields["appointment_date_time"] = analysis["appointment_date_time"]
                    if analysis.get("doctor"):
                        client_custom_fields["doctor"] = analysis["doctor"]
                    if analysis.get("hospital_location"):
                        client_custom_fields["hospital_location"] = analysis["hospital_location"]

                except Exception as analysis_err:
                    logger.error(f"Analysis failed in worker: {analysis_err}", exc_info=True)
                    summary_text = f"Call completed. Analysis unavailable."

        webhook_payload = {
            "event": "CALL_DATA_UPDATE",
            "data": {
                "client_id": call_payload.get("lead_id"),
                "call_id": call_payload.get("call_id") or call_payload.get("voice_id"),
                "call_status": call_status,
                "call_transcript": transcript_data,
                "ai_summary": summary_text,
                "recording_url": recording_url,
                "call_duration_seconds": duration,
                "next_call_on": normalize_to_iso8601(next_call_on) if next_call_on else None,
                "called_on": call_state.get("call_initiated_at") or None,
                "ai_call_id": job_id,
                "process_id": call_payload.get("process_id"),
                "new_stage_id": new_stage_id,
                "metadata": call_payload.get("metadata", {}),
                "client_custom_fields": client_custom_fields or {},
                "call_custom_fields": call_payload.get("call_custom_fields", {}),
                "tos_task_id": call_state.get("tos_task_id")
            }
        }

        # Update audit log
        _run_async(update_webhook_event(event_id, status="processed", result_payload=webhook_payload))

        # Enqueue to delivery worker
        deliver_postcall.delay(event_id, webhook_payload)
        logger.info(f"Post-call processing finished for event_id={event_id}. Handed off to deliver_postcall.")

    except Exception as exc:
        logger.error(f"Error in process_postcall task: {exc}", exc_info=True)
        _run_async(update_webhook_event(event_id, status="failed", error_message=str(exc)))
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=5,
    name="mantra.webhook_tasks.deliver_postcall"
)
def deliver_postcall(self, event_id: str, webhook_payload: Dict[str, Any]):
    """
    Worker Task (webhook_delivery queue):
    1. SAVES payload in local PostgreSQL DB FIRST (call_logs + webhook_events).
       If DB save fails, raises exception to abort delivery and retry later.
    2. Performs data integrity check on processed payload before sending to n8n.
    3. Sends payload to MantraAssist / n8n backend with HMAC signing.
    4. Checks delivery response: if n8n delivery fails, marks status in DB and raises Celery retry.
    5. Reports TOS telemetry log.
    """
    from mantra.utils import update_webhook_event, send_to_backend, save_call_log_to_db, report_telemetry

    logger.info(f"Delivering post-call webhook: event_id={event_id}")
    data = webhook_payload.get("data", {}) if isinstance(webhook_payload, dict) else {}
    call_id = data.get("call_id") or "unknown"
    call_status = data.get("call_status", "Unknown")
    recording_url = data.get("recording_url", "")
    tos_task_id = data.get("tos_task_id")

    # STEP 1: Save payload in local PostgreSQL DB FIRST
    try:
        _run_async(update_webhook_event(event_id, status="saving_to_db", increment_attempts=True))
        _run_async(
            save_call_log_to_db(
                call_id=str(call_id),
                call_log=json.dumps(webhook_payload, indent=2),
                status=f"processed_{call_status}",
                recording_url=recording_url or ""
            )
        )
        _run_async(update_webhook_event(event_id, status="saved_in_db", result_payload=webhook_payload))
        logger.info(f"Successfully saved post-call payload in DB for call_id={call_id}")
    except Exception as db_err:
        logger.error(f"STEP 1 FAILED — Could not save payload to DB for call_id={call_id}: {db_err}", exc_info=True)
        _run_async(update_webhook_event(event_id, status="db_save_failed", error_message=str(db_err)))
        # Abort delivery attempt and retry DB save
        raise self.retry(exc=db_err)

    # STEP 2: Data Integrity & Completeness Check before n8n delivery
    is_valid, validation_error = _verify_payload_integrity(webhook_payload)
    if not is_valid:
        logger.error(f"STEP 2 FAILED — Payload integrity check failed for event_id={event_id}: {validation_error}")
        _run_async(update_webhook_event(event_id, status="invalid_payload", error_message=validation_error))
        raise ValueError(f"Payload integrity check failed: {validation_error}")

    # STEP 3: Deliver to n8n / MantraAssist backend & check delivery status
    try:
        _run_async(update_webhook_event(event_id, status="delivering_to_n8n"))
        logger.info(f"Delivering payload to n8n backend for call_id={call_id}...")
        delivered = _run_async(send_to_backend(webhook_payload))

        if delivered:
            # Mark DB as successfully delivered
            _run_async(update_webhook_event(event_id, status="delivered"))
            _run_async(
                save_call_log_to_db(
                    call_id=str(call_id),
                    call_log=json.dumps(webhook_payload, indent=2),
                    status=f"delivered_{call_status}",
                    recording_url=recording_url or ""
                )
            )
            logger.info(f"STEP 3 SUCCESS — Webhook delivered to n8n for event_id={event_id}, call_id={call_id}")

            if tos_task_id:
                _run_async(
                    report_telemetry(
                        tos_task_id=tos_task_id,
                        message=f"[Delivery Worker] data_sent_to_backend — status={call_status}, delivered=yes",
                        call_id=str(call_id)
                    )
                )
        else:
            # Delivery returned False (e.g. n8n endpoint down, 500 error, network timeout)
            error_msg = f"n8n backend endpoint delivery returned False (HTTP error or timeout) for call_id={call_id}"
            logger.warning(f"STEP 3 WARNING — {error_msg}")
            _run_async(update_webhook_event(event_id, status="delivery_failed", error_message=error_msg))

            if tos_task_id:
                _run_async(
                    report_telemetry(
                        tos_task_id=tos_task_id,
                        message=f"[Delivery Worker] data_sent_to_backend — status={call_status}, delivered=no (retrying)",
                        call_id=str(call_id)
                    )
                )

            # Raise exception to trigger Celery retry
            raise Exception(error_msg)

    except Exception as exc:
        logger.error(f"Delivery exception for event_id={event_id}: {exc}", exc_info=True)
        _run_async(update_webhook_event(event_id, status="delivery_failed", error_message=str(exc)))
        raise self.retry(exc=exc)


def _verify_payload_integrity(webhook_payload: Dict[str, Any]) -> (bool, str):
    """Verify processed payload contains all necessary structure before sending to n8n."""
    if not isinstance(webhook_payload, dict):
        return False, "Payload is not a dictionary"
    
    if webhook_payload.get("event") != "CALL_DATA_UPDATE":
        return False, f"Invalid event type: {webhook_payload.get('event')}"
    
    data = webhook_payload.get("data")
    if not isinstance(data, dict):
        return False, "Payload 'data' field missing or not a dict"
    
    if not data.get("call_id"):
        return False, "Payload 'data.call_id' is missing or empty"
    
    if not data.get("call_status"):
        return False, "Payload 'data.call_status' is missing or empty"

    return True, ""


def start_processing_worker():
    """Start Celery worker for processing queue."""
    celery_app.worker_main(["worker", "--loglevel=info", "-Q", "webhook_processing", "-c", "2"])


def start_delivery_worker():
    """Start Celery worker for delivery queue."""
    celery_app.worker_main(["worker", "--loglevel=info", "-Q", "webhook_delivery", "-c", "2"])
