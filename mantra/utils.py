import os
import io
import json
import time
import hmac
import hashlib
import asyncio
import datetime
import logging
import httpx
import numpy as np
import asyncpg
from typing import Dict, List, Optional

from livekit import rtc
from livekit.agents import llm
import boto3

logger = logging.getLogger("mantra.utils")


def format_e164_phone_number(phone_num: str, country_code: str = "") -> str:
    """Format phone number to E.164 with leading + sign and country code."""
    if not phone_num:
        return ""
    num = str(phone_num).strip()
    if not num:
        return ""
    if num.startswith("+"):
        return num
    
    clean = "".join([c for c in num if c.isdigit()])
    if not clean:
        return num

    cc = "".join([c for c in str(country_code) if c.isdigit()]) if country_code else ""
    
    if cc and clean.startswith(cc) and len(clean) > len(cc):
        return f"+{clean}"
    elif len(clean) == 10 and cc:
        return f"+{cc}{clean}"
    elif len(clean) == 10 and not cc:
        return f"+91{clean}"
    else:
        return f"+{clean}"


async def save_call_log_to_db(
    call_id: str,
    call_log: str,
    status: str,
    recording_url: str,
    caller_number: str = "",
    called_number: str = "",
    trunk_id: str = "",
):
    """Save call details to the isolated PostgreSQL logging database."""
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")
    db_host = os.getenv("POSTGRES_HOST")
    db_port = os.getenv("POSTGRES_PORT")

    conn = None
    try:
        logger.info(
            f"Attempting to connect to PostgreSQL at {db_host}:{db_port} for call_id: {call_id}..."
        )
        conn = await asyncpg.connect(
            user=db_user,
            password=db_password,
            database=db_name,
            host=db_host,
            port=db_port,
            timeout=5.0,
        )
        logger.info(f"Successfully connected to PostgreSQL at {db_host}:{db_port}")

        # Parse call_log to extract attempt metadata
        log_data = {}
        try:
            log_data = json.loads(call_log) if isinstance(call_log, str) else call_log
        except Exception:
            pass

        attempted_at = (
            log_data.get("called_on")
            or log_data.get("requested_at")
            or datetime.now(tz=timezone.utc).isoformat()
        )
        ai_call_id = log_data.get("ai_call_id") or log_data.get("data", {}).get("ai_call_id") or ""
        duration = log_data.get("call_duration") or log_data.get("call_duration_seconds") or 0

        attempt_entry = {
            "attempted_at": attempted_at,
            "status": status,
            "ai_call_id": ai_call_id,
            "duration": duration,
            "recording_url": recording_url or "",
            "summary": log_data.get("ai_summary") or "",
            "payload": log_data,
        }

        # Auto-ensure attempts column exists
        await conn.execute("ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS attempts JSONB DEFAULT '[]'::jsonb;")

        # Insert or update the call log, appending the attempt entry to attempts JSONB array
        query = """
        INSERT INTO call_logs (call_id, call_log, status, recording_url, caller_number, called_number, trunk_id, attempts)
        VALUES ($1, $2, $3, $4, $5, $6, $7, jsonb_build_array($8::jsonb))
        ON CONFLICT (call_id) DO UPDATE 
        SET call_log = EXCLUDED.call_log,
            status = EXCLUDED.status,
            recording_url = EXCLUDED.recording_url,
            caller_number = EXCLUDED.caller_number,
            called_number = EXCLUDED.called_number,
            trunk_id = EXCLUDED.trunk_id,
            attempts = COALESCE(call_logs.attempts, '[]'::jsonb) || jsonb_build_array($8::jsonb)
        """
        await conn.execute(query, call_id, call_log, status, recording_url, caller_number, called_number, trunk_id, json.dumps(attempt_entry))
        logger.info(f"Successfully saved call log to DB for call_id: {call_id}")
    except Exception as e:
        logger.error(f"Failed to save call log to DB: {e}")
    finally:
        if conn:
            await conn.close()


async def save_call_event(
    call_id: str,
    event_type: str,
    event_source: str,
    event_payload: dict,
    event_status: str = "success",
    event_error: str = "",
    event_log: str = "",
    ai_call_id: str = "",
):
    """Save a single call-lifecycle event to the call_events audit table.

    event_type examples:
      webhook_received, dispatch_created, sip_initiated, sip_connected,
      sip_failed, entrypoint_started, backend_sent, backend_failed

    event_source: 'ui_server' | 'agent'
    """
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")
    db_host = os.getenv("POSTGRES_HOST")
    db_port = os.getenv("POSTGRES_PORT")

    if not all([db_user, db_password, db_name, db_host, db_port]):
        return

    extracted_ai_call_id = (
        ai_call_id
        or (event_payload.get("ai_call_id") if isinstance(event_payload, dict) else "")
        or (event_payload.get("job_id") if isinstance(event_payload, dict) else "")
        or (event_payload.get("data", {}).get("ai_call_id") if isinstance(event_payload, dict) and isinstance(event_payload.get("data"), dict) else "")
        or ""
    )

    conn = None
    try:
        conn = await asyncpg.connect(
            user=db_user,
            password=db_password,
            database=db_name,
            host=db_host,
            port=db_port,
            timeout=3.0,
        )
        try:
            await conn.execute(
                """
                INSERT INTO call_events (call_id, event_type, event_source, event_payload, event_log, event_status, event_error, ai_call_id)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
                ON CONFLICT (call_id, event_type) DO UPDATE
                SET event_payload = EXCLUDED.event_payload,
                    event_log     = EXCLUDED.event_log,
                    event_status  = EXCLUDED.event_status,
                    event_error   = EXCLUDED.event_error,
                    ai_call_id    = EXCLUDED.ai_call_id;
                """,
                str(call_id),
                event_type,
                event_source,
                json.dumps(event_payload, default=str),
                str(event_log or "")[:8000],
                event_status,
                event_error or "",
                str(extracted_ai_call_id or ""),
            )
        except asyncpg.UniqueViolationError as uve:
            if "call_events_pkey" in str(uve):
                logger.info(f"Detected out-of-sync PostgreSQL sequence for call_events (key={uve}), repairing sequence...")
                await conn.execute("SELECT setval(pg_get_serial_sequence('call_events', 'id'), COALESCE(MAX(id), 1)) FROM call_events;")
                # Retry after sequence sync
                await conn.execute(
                    """
                    INSERT INTO call_events (call_id, event_type, event_source, event_payload, event_log, event_status, event_error)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
                    ON CONFLICT (call_id, event_type) DO UPDATE
                    SET event_payload = EXCLUDED.event_payload,
                        event_log     = EXCLUDED.event_log,
                        event_status  = EXCLUDED.event_status,
                        event_error   = EXCLUDED.event_error;
                    """,
                    str(call_id),
                    event_type,
                    event_source,
                    json.dumps(event_payload, default=str),
                    str(event_log or "")[:8000],
                    event_status,
                    event_error or "",
                )
            else:
                raise
    except Exception as e:
        logger.warning(f"Failed to save call event {event_type}/{call_id}: {e}")
    finally:
        if conn:
            await conn.close()


async def _claim_backend_delivery(dedupe_key: str, force: bool = False) -> bool:
    """First writer wins per dedupe_key (call_id + ai_call_id). Prevents ui_server + agent double-webhooks."""
    if not dedupe_key:
        return True
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return True
    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, decode_responses=True)
        try:
            if force:
                await client.delete(f"backend_sent:{dedupe_key}")
            claimed = await client.set(f"backend_sent:{dedupe_key}", "1", nx=True, ex=300)
            if not claimed and not force:
                logger.info(
                    f"Backend webhook already claimed for dedupe_key={dedupe_key} — skipping duplicate"
                )
            return bool(claimed) or force
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning(f"backend delivery claim failed for dedupe_key={dedupe_key}, allowing send: {e}")
        return True


async def _release_backend_delivery(dedupe_key: str) -> None:
    """Allow a retry if the claimed delivery never succeeded."""
    if not dedupe_key:
        return
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return
    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, decode_responses=True)
        try:
            await client.delete(f"backend_sent:{dedupe_key}")
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning(f"backend delivery release failed for dedupe_key={dedupe_key}: {e}")


async def send_to_backend(payload: dict, max_retries: int = 3, force: bool = False) -> bool:
    """POST the post-call payload to the MantraAssist backend with HMAC signing.

    Dedupes by call_id + ai_call_id via Redis SET NX so only one of ui_server/agent delivers per attempt.
    """
    base_url = os.getenv("MANTRAASSIST_BACKEND_URL", "").rstrip("/")
    webhook_secret = os.getenv("MANTRAASSIST_WEBHOOK_SECRET", "")

    if not base_url:
        logger.warning("MANTRAASSIST_BACKEND_URL not set — skipping backend webhook")
        return False

    call_id = ""
    ai_call_id = ""
    event_type = ""
    try:
        if isinstance(payload, dict):
            event_type = payload.get("event", "")
            data = payload.get("data")
            if isinstance(data, dict):
                call_id = str(data.get("call_id") or "")
                ai_call_id = str(data.get("ai_call_id") or "")
    except Exception:
        call_id = ""

    dedupe_key = f"{call_id}_{ai_call_id}" if (call_id and ai_call_id) else call_id
    is_retry_payload = force or (event_type in ("CALL_RETRY", "call_retry"))

    if not await _claim_backend_delivery(dedupe_key, force=is_retry_payload):
        return True  # already delivered (or in-flight) by the other path

    url = f"{base_url}/api/v1/webhooks/n8n"

    timestamp = str(int(time.time()))

    timestamp_iso = datetime.datetime.utcfromtimestamp(int(timestamp)).strftime("%Y-%m-%dT%H:%M:%S")

    if not payload:
        payload_str = '{}'
    else:
        payload_str = json.dumps(payload, separators=(',', ':'))
    logger.info(f"Payload: {payload_str}")

    data_to_sign = f"{payload_str}.{timestamp}"

    headers = {
        "Content-Type": "application/json",
        "x-timestamp": timestamp,
        "x-source": "n8n",
        "x-timestamp-iso": timestamp_iso
    }

    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers["x-signature"] = signature
        logger.info(f"Signing request with HMAC (timestamp: {timestamp})")
    else:
        logger.warning("MANTRAASSIST_WEBHOOK_SECRET not set — sending unsigned request")

    logger.info(f"Delivering post-call webhook to: {url} call_id={call_id or 'unknown'}")

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, content=payload_str, headers=headers)
                resp.raise_for_status()
                logger.info(
                    f"Backend webhook delivered successfully (HTTP {resp.status_code}) call_id={call_id or 'unknown'}"
                )
                
                # Persist delivered payload to PostgreSQL call_logs table
                try:
                    data_obj = payload.get("data") if isinstance(payload, dict) else {}
                    if isinstance(data_obj, dict) and call_id:
                        status_val = str(data_obj.get("call_status") or data_obj.get("status") or "Completed")
                        recording_val = str(data_obj.get("recording_url") or data_obj.get("s3_recording") or "")
                        caller_num = str(data_obj.get("caller_number") or data_obj.get("client_phone") or "")
                        called_num = str(data_obj.get("called_number") or "")
                        trunk_val = str(data_obj.get("trunk_id") or data_obj.get("sip_trunk_id") or "")
                        
                        await save_call_log_to_db(
                            call_id=call_id,
                            call_log=json.dumps(data_obj),
                            status=status_val,
                            recording_url=recording_val,
                            caller_number=caller_num,
                            called_number=called_num,
                            trunk_id=trunk_val
                        )
                except Exception as db_err:
                    logger.warning(f"Failed to persist delivered webhook payload to DB for call_id={call_id}: {db_err}")

                return True
        except Exception as e:
            logger.error(f"Backend webhook attempt {attempt}/{max_retries} failed: {e}")

        if attempt < max_retries:
            await asyncio.sleep(2 ** (attempt - 1))

    await _release_backend_delivery(dedupe_key)
    return False


def upload_to_s3(file_bytes: bytes, s3_key: str) -> Optional[str]:
    """Upload bytes to S3 and return the public URL."""
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    region = os.getenv("AWS_REGION", "us-east-1")

    if not bucket_name:
        logger.warning("AWS_S3_BUCKET_NAME not set — skipping upload")
        return None

    # Strip proxy env vars so requests/urllib3 doesn't pick them up
    _saved = {}
    for _var in (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "https_proxy",
        "http_proxy",
        "PLIVO_PROXY",
    ):
        _val = os.environ.pop(_var, None)
        if _val is not None:
            _saved[_var] = _val

    try:
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        s3_kwargs = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            s3_kwargs["aws_access_key_id"] = aws_access_key_id
            s3_kwargs["aws_secret_access_key"] = aws_secret_access_key

        s3 = boto3.client("s3", **s3_kwargs)
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_bytes,
            ContentType="audio/mpeg",
            ACL="public-read",
        )
        url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
        logger.info(f"Uploaded recording to S3: {url}")
        return url
    except Exception as e:
        logger.error(f"S3 upload failed: {e}", exc_info=True)
        return None
    finally:
        os.environ.update(_saved)


class SessionRecorder:
    """Namespace for call recording utilities: transcript building, summary, analysis."""
    
    def __init__(self):
        self._tracks: Dict[str, List[bytes]] = {}
        self._recording_tasks: List[asyncio.Task] = []
        self.start_time = datetime.datetime.now()
        self.end_time = None
        self.recording_duration_seconds = 0.0

        self.SAMPLE_RATE = 48000
        self.NUM_CHANNELS = 1
        self.SAMPLE_WIDTH = 2  # 16-bit

    def start_recording(self, track: rtc.Track, label: str):
        track_id = track.sid or str(id(track))
        if track_id in self._tracks:
            return
        self._tracks[track_id] = []
        task = asyncio.create_task(self._consume_track(track, track_id, label))
        self._recording_tasks.append(task)

    async def _consume_track(self, track: rtc.Track, track_id: str, label: str):
        audio_stream = rtc.AudioStream(
            track, sample_rate=self.SAMPLE_RATE, num_channels=self.NUM_CHANNELS
        )
        try:
            async for frame_event in audio_stream:
                self._tracks[track_id].append(bytes(frame_event.frame.data))
        except Exception as e:
            logger.error(f"Error recording track {label}: {e}")
        finally:
            await audio_stream.aclose()

    async def stop_recording(self):
        self.end_time = datetime.datetime.now()
        cancelled = []
        for task in self._recording_tasks:
            if not task.done():
                task.cancel()
                cancelled.append(task)
        if cancelled:
            await asyncio.gather(*cancelled, return_exceptions=True)
        self._recording_tasks.clear()

    def get_combined_mp3_bytes(self) -> bytes:
        self.end_time = datetime.datetime.now()
        if not self._tracks:
            return b""

        track_arrays = []
        for frames in self._tracks.values():
            if frames:
                track_arrays.append(np.frombuffer(b"".join(frames), dtype=np.int16))

        if not track_arrays:
            return b""

        max_len = max(len(a) for a in track_arrays)
        mixed = np.zeros(max_len, dtype=np.float32)
        for arr in track_arrays:
            if len(arr) < max_len:
                arr = np.pad(arr, (0, max_len - len(arr)), mode="constant")
            mixed += arr.astype(np.float32)
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)

        try:
            from pydub import AudioSegment
            from pydub.silence import detect_nonsilent

            audio = AudioSegment(
                mixed.tobytes(),
                frame_rate=self.SAMPLE_RATE,
                sample_width=self.SAMPLE_WIDTH,
                channels=self.NUM_CHANNELS,
            )
            nonsilent = detect_nonsilent(
                audio, min_silence_len=200, silence_thresh=-40, seek_step=10
            )
            if nonsilent:
                start_ms = nonsilent[0][0]
                if start_ms > 0:
                    audio = audio[start_ms:]

            self.recording_duration_seconds = len(audio) / 1000.0

            buf = io.BytesIO()
            audio.export(buf, format="mp3", bitrate="128k")
            return buf.getvalue()
        except Exception as e:
            logger.error(f"MP3 conversion failed: {e}")
            return b""

    @staticmethod
    def build_transcript(history: list, handoff_info: dict = None) -> str:
        structured = []
        for msg in history:
            role = msg.role.name if hasattr(msg.role, "name") else str(msg.role)
            content = (
                " ".join([str(c) for c in msg.content])
                if isinstance(msg.content, list)
                else msg.content
            )
            if content and not content.startswith("[System:"):
                role_label = "bot" if role.lower() == "assistant" else "user"
                structured.append({role_label: content})
        if handoff_info:
            structured.append({"handoff": handoff_info})
            structured.append({"info": "Speech after this point is human agent conversation, not yet transcribed"})
        return json.dumps(structured)

    @staticmethod
    async def generate_summary(llm_engine: llm.LLM, history: list) -> str:
        summary_prompt = (
            "Generate a call summary as a single, coherent paragraph. It must properly state: "
            "what the patient concern/reason for calling was, the details discussed in the call, "
            "the conclusion, and any other important patient details based on the transcript. "
            "Keep it concise but detailed. Here is the transcript:\n"
        )
        for msg in history:
            role = msg.role.name if hasattr(msg.role, "name") else str(msg.role)
            content = (
                " ".join([str(c) for c in msg.content])
                if isinstance(msg.content, list)
                else msg.content
            )
            if content and not content.startswith("[System:"):
                summary_prompt += f"{role.upper()}: {content}\n"

        try:
            messages = [
                llm.ChatMessage(
                    role="system", content=["You are a helpful assistant."]
                ),
                llm.ChatMessage(role="user", content=[summary_prompt]),
            ]
            stream = llm_engine.chat(chat_ctx=llm.ChatContext(items=messages))
            response = await asyncio.wait_for(stream.collect(), timeout=45.0)

            import re

            clean_text = re.sub(r"[*#_~`\[\]]", "", response.text)
            clean_text = clean_text.encode("ascii", "ignore").decode("ascii")
            lines = [
                " ".join(line.split())
                for line in clean_text.splitlines()
                if line.strip()
            ]
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Summary failed: {e}")
            return ""

    @staticmethod
    async def analyze_call(
        llm_engine: llm.LLM,
        history: list,
        current_stage_id: Optional[int],
        stage_details: List[dict],
        duration: int,
        client_country_code: str = "",
        process_stage_data: Optional[list] = None,
    ) -> dict:
        # Fallback values
        fallback_stage_id = current_stage_id

        # Parse stage details to find fallback IDs based on rules
        not_answering_id = None
        interested_id = None
        confirmed_id = None
        follow_up_id = None
        not_interested_id = None
        
        for stage in stage_details:
            desc = stage.get("description", "").lower()
            sid = stage.get("stage_id")
            if "not answering" in desc or "failed" in desc or "incomplete" in desc:
                not_answering_id = sid
            elif "shown interest" in desc or "interested" in desc:
                pass
            elif "confirmed" in desc or "appointment date" in desc:
                pass
            elif "follow up" in desc or "call later" in desc:
                follow_up_id = sid
            elif "not interested" in desc or "no further follow" in desc:
                pass

        # Construct transcript
        transcript_lines = []
        for msg in history:
            role = msg.role.name if hasattr(msg.role, "name") else str(msg.role)
            content = (
                " ".join([str(c) for c in msg.content])
                if isinstance(msg.content, list)
                else msg.content
            )
            if content and not content.startswith("[System:"):
                role_label = "Assistant" if role.lower() == "assistant" else "User"
                transcript_lines.append(f"{role_label}: {content}")
        transcript_text = "\n".join(transcript_lines)

        current_time = datetime.datetime.now()
        current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

        process_blocks = []
        if stage_details:
            process_blocks.append(
                f"--- AVAILABLE CRM STAGES ---\n{json.dumps(stage_details, indent=2)}"
            )
        if process_stage_data:
            process_blocks.append(
                f"--- AVAILABLE PROCESSES (with stages) ---\n{json.dumps(process_stage_data, indent=2)}"
            )
        process_block = "\n\n".join(process_blocks)

        prompt = f"""
You are an expert analyst for a care support and CRM system. Analyze the phone call transcript and metadata below.

--- CALL METADATA ---
Current Date and Time (Server Local Time): {current_time_str}
Call Duration: {duration} seconds
Current Stage ID: {current_stage_id}
Client Country Code: {client_country_code}

{process_block}

--- TRANSCRIPT ---
{transcript_text}

--- ANALYSIS TASK ---
1. Generate a call summary as a single, coherent paragraph. It must properly state:
   - What the patient concern/reason for calling was.
   - The details discussed in the call.
   - The conclusion (e.g. appointment booked, demo requested, callback scheduled, disconnected, not interested).
   - Any other important patient details based on the transcript.
2. Determine the correct process_id and next stage_id.
   - If `AVAILABLE CRM STAGES` is provided:
     * You MUST select `new_stage_id` from the `stage_id` values listed in `AVAILABLE CRM STAGES`.
     * Carefully compare every stage's `description` in `AVAILABLE CRM STAGES` against what happened in the call transcript:
       - If the patient confirmed an appointment date/time or agreed/confirmed to visit a branch (e.g. Paschim Vihar, Noida, Gurugram, etc.), select the stage for appointment confirmation / visit confirmed (e.g. stage_id where description mentions confirmed appointment/visit).
       - If the patient requested a callback or to follow up later (e.g. "call me back later", "call tomorrow", "busy right now"), select the stage for follow-up / call later.
       - If the patient declined, stated they are not interested in eye checkup/visit, or pricing/location didn't match, select the stage for not interested / declined.
       - If the patient confirmed treatment/visit is already done, select the stage for treatment/visit completed.
       - If the patient was not responding or call failed, select the stage for not answering / failed.
     * If no stage transition criteria are met or the call was purely informational with no state change, default `new_stage_id` to current stage ID: {current_stage_id}.
   - If `AVAILABLE CRM STAGES` is not provided but `AVAILABLE PROCESSES` is provided:
     * Select `process_id` and `new_stage_id` from `AVAILABLE PROCESSES` based on the matching process and stage descriptions.
   - If neither is provided or no stage transition occurred, set `new_stage_id` to {current_stage_id}.
3. Extract additional metadata:
   - `next_call_on`: If a follow-up or callback is requested or scheduled (e.g. "call me back in 10 minutes", "call back in 1 hour", "call tomorrow at 3 PM"), calculate the EXACT future timestamp by adding that offset/duration to Current Date and Time ({current_time_str}) and return it in "YYYY-MM-DD HH:MM:SS" format. If the stage description specifies adding 24 hours, add 24 hours to {current_time_str}. If no follow-up is needed, use null.
   - `appointment_date_time`: If the patient booked/confirmed/rescheduled an appointment, extract the date/time and convert to the server's local timezone (e.g., "2026-06-05 11:30:00"). Otherwise, use null.
   - `doctor`: Extract any mentioned doctor's name. Otherwise, use null.
   - `hospital_location`: Extract the preferred hospital location/center name. Otherwise, use null.
   - `user_intent`: Determine the primary caller intent from the call transcript and outcome:
     - "APPOINTMENT_BOOKED": If the conversation outcome is positive — e.g. the user agreed to/booked an appointment, checkup, visit, or live demo (such as demo booked or requested).
     - "APPOINTMENT_CANCELLED": If the user explicitly cancelled an appointment/booking.
     - "APPOINTMENT_RESCHEDULED": If the user rescheduled an appointment/booking to a new date/time.
     - Otherwise, null.
   - `sentiment_score`: Rate the user's sentiment from 0.0 (very negative/angry) to 1.0 (very positive/happy), with 0.5 as neutral.

You MUST return your response as a valid JSON object with the following schema:
{{
  "summary": "string (a single paragraph call summary)",
  "process_id": integer or null (the selected process ID from AVAILABLE PROCESSES, or null if no processes available),
  "new_stage_id": integer (the selected stage ID from the list),
  "next_call_on": "string or null",
  "appointment_date_time": "string or null",
  "doctor": "string or null",
  "hospital_location": "string or null",
  "user_intent": "APPOINTMENT_BOOKED" or "APPOINTMENT_CANCELLED" or "APPOINTMENT_RESCHEDULED" or null,
  "sentiment_score": float
}}

Provide ONLY the JSON object. Do not include markdown code block syntax or other text wrapper.
"""

        try:
            messages = [
                llm.ChatMessage(
                    role="system", content=["You are a helpful assistant."]
                ),
                llm.ChatMessage(role="user", content=[prompt]),
            ]
            stream = llm_engine.chat(chat_ctx=llm.ChatContext(items=messages))
            response = await asyncio.wait_for(stream.collect(), timeout=60.0)

            text = response.text.strip()
            res_dict = None
            if text.startswith("```"):
                open_idx = text.find("\n")
                end_idx = text.rfind("```")
                if open_idx != -1:
                    text = text[open_idx + 1:]
                if end_idx != -1:
                    text = text[:end_idx]
                text = text.strip()
            try:
                res_dict = json.loads(text)
            except json.JSONDecodeError:
                # Extract the first balanced { ... } object if the model wrapped
                # the JSON with prose or partial fences.
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end > start:
                    candidate = text[start:end + 1]
                    res_dict = json.loads(candidate)
                else:
                    raise

            if not isinstance(res_dict, dict):
                start = text.find("{")
                end = text.rfind("}")
                candidate = text[start:end + 1]
                res_dict = json.loads(candidate)

            summary = res_dict.get("summary") or ""
            process_id = res_dict.get("process_id")
            new_stage_id = res_dict.get("new_stage_id")
            next_call_on = res_dict.get("next_call_on")
            appointment_date_time = res_dict.get("appointment_date_time")
            doctor = res_dict.get("doctor")
            hospital_location = res_dict.get("hospital_location")
            sentiment_score = res_dict.get("sentiment_score", 0.5)
            user_intent_raw = res_dict.get("user_intent") or res_dict.get("call_intent")
            if user_intent_raw:
                ui_str = str(user_intent_raw).strip().upper()
                if ui_str in ["APPOINTMENT_BOOKED", "DEMO_BOOKED", "DEMO_REQUESTED", "POSITIVE_INTENT"]:
                    user_intent = "APPOINTMENT_BOOKED"
                elif ui_str in ["APPOINTMENT_CANCELLED", "CANCELLED"]:
                    user_intent = "APPOINTMENT_CANCELLED"
                elif ui_str in ["APPOINTMENT_RESCHEDULED", "RESCHEDULED"]:
                    user_intent = "APPOINTMENT_RESCHEDULED"
                else:
                    user_intent = None
            else:
                user_intent = None

            if process_id is not None:
                try:
                    process_id = int(process_id)
                except (ValueError, TypeError):
                    process_id = None

            if new_stage_id is not None:
                try:
                    new_stage_id = int(new_stage_id)
                except (ValueError, TypeError):
                    new_stage_id = fallback_stage_id
            else:
                new_stage_id = fallback_stage_id

            if not summary:
                summary = await SessionRecorder.generate_summary(llm_engine, history)

        except Exception as e:
            logger.error(
                f"analyze_call failed: {e}. Falling back to default heuristics."
            )
            summary = await SessionRecorder.generate_summary(llm_engine, history)
            new_stage_id = fallback_stage_id
            process_id = None
            next_call_on = None
            appointment_date_time = ""
            doctor = ""
            hospital_location = ""
            sentiment_score = 0.5
            user_intent = None

        return {
            "summary": summary,
            "process_id": process_id,
            "new_stage_id": new_stage_id,
            "next_call_on": next_call_on,
            "appointment_date_time": appointment_date_time,
            "doctor": doctor,
            "hospital_location": hospital_location,
            "user_intent": user_intent,
            "sentiment_score": sentiment_score,
        }

    @staticmethod
    def parse_summary_data(summary_text: str):
        sentiment_score = 0.5
        next_call_on = None
        custom_fields = {
            "appointment_date_time": "",
            "doctor": "",
            "hospital_location": "",
        }
        try:
            for line in summary_text.split("\n"):
                line = line.strip()
                if "Sentiment Score:" in line:
                    sentiment_score = float(line.split(":")[1].strip().split()[0])
                elif "Next Call Date:" in line:
                    val = line.replace("Next Call Date:", "").strip().strip("*-• ")
                    if val.lower() not in ["none", "n/a", "null"] and len(val) > 5:
                        next_call_on = val
                elif "Appointment Date & Time:" in line:
                    val = line.split(":", 1)[1].strip().strip("*-• \"'")
                    if val.lower() not in ["none", "n/a", "null", ""]:
                        custom_fields["appointment_date_time"] = val
                elif "Doctor:" in line:
                    val = line.split(":", 1)[1].strip().strip("*-• \"'")
                    if val.lower() not in ["none", "n/a", "null", ""]:
                        custom_fields["doctor"] = val
                elif "Hospital Location:" in line:
                    val = line.split(":", 1)[1].strip().strip("*-• \"'")
                    if val.lower() not in ["none", "n/a", "null", ""]:
                        custom_fields["hospital_location"] = val
        except:
            pass
        return sentiment_score, next_call_on, custom_fields


async def report_telemetry(
    tos_task_id: str,
    message: str,
    call_id: str = None,
    level: str = "info",
    tos_token: str = None,
    data: dict = None,
) -> bool:
    tos_url = os.getenv("TOS_ENDPOINT", "").rstrip("/")
    if not tos_url:
        logger.error("TOS_ENDPOINT environment variable not set. Cannot send telemetry.")
        return False

    url = f"{tos_url}/api/telemetry/{tos_task_id}/log"
    token = tos_token or os.getenv("TOS_SERVICE_SECRET", "")

    body = {"level": level, "message": message}
    if call_id:
        body["call_id"] = str(call_id)
    if data:
        body["data"] = data

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(proxy=None, timeout=10.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            if not resp.is_success:
                logger.warning(f"TOS telemetry failed with status {resp.status_code} for task {tos_task_id}.")
                return False
            return True
    except httpx.RequestError as e:
        logger.error(f"TOS telemetry request error for task {tos_task_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"TOS telemetry error for task {tos_task_id}: {e}", exc_info=True)
        return False


def normalize_datetime(dt_str: Optional[str]) -> Optional[str]:
    """Convert datetime string to 'YYYY-MM-DDTHH:MM:SSZ' format for payloads."""
    if not dt_str:
        return None
    val = str(dt_str).strip()
    if not val or val.lower() in ("null", "none", "n/a", ""):
        return None
    val = val.replace(" ", "T")
    if not val.endswith("Z"):
        val += "Z"
    return val
