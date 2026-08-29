"""In-memory session audio recording, transcript generation, LLM post-call analysis, and delivery."""

import io
import json
import asyncio
import datetime
import logging
from typing import Dict, List, Optional
import numpy as np
from livekit import rtc
from livekit.agents import llm, APIConnectOptions

logger = logging.getLogger("services.session_recorder")


class SessionRecorder:
    """Namespace for call recording utilities: audio stream recording, transcript building, summary, analysis."""

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
            stream = llm_engine.chat(
                chat_ctx=llm.ChatContext(items=messages),
                conn_options=APIConnectOptions(timeout=60.0, max_retry=3, retry_interval=2.0),
            )
            response = await asyncio.wait_for(stream.collect(), timeout=60.0)

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
        fallback_stage_id = current_stage_id

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
       - If the patient confirmed an appointment date/time or agreed/confirmed to visit a branch, select the stage for appointment confirmation / visit confirmed.
       - If the patient requested a callback or to follow up later, select the stage for follow-up / call later.
       - If the patient declined, stated they are not interested, select the stage for not interested / declined.
       - If the patient confirmed treatment/visit is already done, select the stage for treatment/visit completed.
       - If the patient was not responding or call failed, select the stage for not answering / failed.
     * If no stage transition criteria are met or the call was purely informational with no state change, default `new_stage_id` to current stage ID: {current_stage_id}.
   - If `AVAILABLE CRM STAGES` is not provided but `AVAILABLE PROCESSES` is provided:
     * Select `process_id` and `new_stage_id` from `AVAILABLE PROCESSES` based on the matching process and stage descriptions.
   - If neither is provided or no stage transition occurred, set `new_stage_id` to {current_stage_id}.
3. Extract additional metadata:
   - `client_name`: Extract ONLY the caller's/user's/patient's own name (the person speaking as "User" in the transcript).
     * Do NOT extract the AI Assistant/Agent's name.
     * Do NOT extract doctor names mentioned in the call.
     * ONLY extract the name given by the caller when identifying themselves.
     * Capitalize properly. If the caller did not state their own name, return null.
   - `next_call_on`: If a follow-up or callback is requested or scheduled, calculate the EXACT future timestamp by adding that offset to Current Date and Time ({current_time_str}) and return it in "YYYY-MM-DD HH:MM:SS" format. If no follow-up is needed, use null.
   - `appointment_date_time`: If the patient booked/confirmed/rescheduled an appointment, extract the date/time (e.g., "2026-06-05 11:30:00"). Otherwise, use null.
   - `doctor`: Extract any mentioned doctor's name. Otherwise, use null.
   - `hospital_location`: Extract the preferred hospital location/center name. Otherwise, use null.
   - `user_intent`: Determine the primary caller intent: "APPOINTMENT_BOOKED", "APPOINTMENT_CANCELLED", "APPOINTMENT_RESCHEDULED", or null.
   - `sentiment_score`: Rate the user's sentiment from 0.0 (very negative/angry) to 1.0 (very positive/happy), with 0.5 as neutral.

You MUST return your response as a valid JSON object with the following schema:
{{
  "summary": "string (a single paragraph call summary)",
  "client_name": "string or null",
  "process_id": integer or null,
  "new_stage_id": integer,
  "next_call_on": "string or null",
  "appointment_date_time": "string or null",
  "doctor": "string or null",
  "hospital_location": "string or null",
  "user_intent": "APPOINTMENT_BOOKED" or "APPOINTMENT_CANCELLED" or "APPOINTMENT_RESCHEDULED" or null,
  "sentiment_score": float
}}

Provide ONLY the JSON object. Do not include markdown code block syntax.
"""

        try:
            messages = [
                llm.ChatMessage(
                    role="system", content=["You are a helpful assistant."]
                ),
                llm.ChatMessage(role="user", content=[prompt]),
            ]
            stream = llm_engine.chat(
                chat_ctx=llm.ChatContext(items=messages),
                conn_options=APIConnectOptions(timeout=60.0, max_retry=3, retry_interval=2.0),
            )
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
            except Exception:
                import re
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    res_dict = json.loads(match.group(0))

            if not res_dict or not isinstance(res_dict, dict):
                return {
                    "summary": "Call completed.",
                    "new_stage_id": fallback_stage_id,
                    "process_id": None,
                    "next_call_on": None,
                    "sentiment_score": 0.5,
                }

            if not res_dict.get("new_stage_id"):
                res_dict["new_stage_id"] = fallback_stage_id
            if "client_name" in res_dict:
                c_name = res_dict["client_name"]
                if c_name:
                    c_name_lower = str(c_name).strip().lower()
                    if (
                        c_name_lower in ["user", "unknown", "n/a", "none", "null", "assistant", "ai assistant", "agent", "mantra"]
                        or "assistant" in c_name_lower
                        or "dr." in c_name_lower
                        or "doctor" in c_name_lower
                    ):
                        res_dict["client_name"] = None
                    else:
                        res_dict["client_name"] = str(c_name).strip().title()

            return res_dict
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {
                "summary": "Call completed.",
                "new_stage_id": fallback_stage_id,
                "process_id": None,
                "next_call_on": None,
                "sentiment_score": 0.5,
            }


__all__ = ["SessionRecorder"]
