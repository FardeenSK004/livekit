"""In-memory call recording, transcript building, and post-call analysis."""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import logging
from typing import Dict, List, Optional

import numpy as np
from livekit import rtc
from livekit.agents import llm

logger = logging.getLogger("app.recording.session_recorder")


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
            logger.error("Error recording track %s: %s", label, e)
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
            logger.error("MP3 conversion failed: %s", e)
            return b""

    @staticmethod
    def build_transcript(history: list, handoff_info: dict | None = None) -> str:
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
            structured.append(
                {
                    "info": "Speech after this point is human agent conversation, not yet transcribed"
                }
            )
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
            response = await stream.collect()

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
            logger.error("Summary failed: %s", e)
            return ""

    @staticmethod
    async def analyze_call(
        llm_engine: llm.LLM,
        history: list,
        current_stage_id: Optional[int],
        stage_details: List[dict],
        duration: int,
        client_country_code: str = "",
    ) -> dict:
        fallback_stage_id = current_stage_id

        not_answering_id = None
        follow_up_id = None

        for stage in stage_details:
            desc = stage.get("description", "").lower()
            sid = stage.get("stage_id")
            if "not answering" in desc or "failed" in desc or "incomplete" in desc:
                not_answering_id = sid
            elif "follow up" in desc or "call later" in desc:
                follow_up_id = sid

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

        prompt = f"""
You are an expert analyst for a care support and CRM system. Analyze the phone call transcript and metadata below.

--- CALL METADATA ---
Current Date and Time (Server Time - IST): {current_time_str}
Call Duration: {duration} seconds
Current Stage ID: {current_stage_id}
Client Country Code: {client_country_code}

--- AVAILABLE CRM STAGES ---
{json.dumps(stage_details, indent=2)}

--- TRANSCRIPT ---
{transcript_text}

--- ANALYSIS TASK ---
1. Generate a call summary as a single, coherent paragraph. It must properly state:
   - What the patient concern/reason for calling was.
   - The details discussed in the call.
   - The conclusion (e.g. appointment booked, callback scheduled, disconnected, not interested).
   - Any other important patient details based on the transcript.
2. Determine the correct Next Stage ID (`new_stage_id`) from the AVAILABLE CRM STAGES above.
   - Select the stage ID whose description best matches the outcome of the call.
   - If the patient confirmed/booked an appointment, select the stage for "confirmed the appointment".
   - If the patient asked to call back or follow up later, select the stage for "follow up or call later".
   - If the patient showed interest but didn't book yet, select the stage for "shown interest".
   - If the patient is not interested or declined, select the stage for "not interested" or the specific declining reason stage.
   - If none of the stages match or the call did not change the state, default to the current stage ID: {current_stage_id}.
3. Extract additional metadata:
   - CRITICAL TIMEZONE INSTRUCTION: If the client discusses times (e.g., 'tomorrow at 3 PM'), interpret them in the client's local timezone based on their Client Country Code '{client_country_code}'. HOWEVER, you MUST convert the final output times for `next_call_on` and `appointment_date_time` into Indian Standard Time (IST, UTC+5:30) in 'YYYY-MM-DD HH:MM:SS' format.
   - `next_call_on`: If a follow-up or callback is scheduled/needed, calculate the exact date and time in IST (e.g., "2026-06-02 15:00:00"). If the stage description specifies adding 24 hours to the current time, add 24 hours to {current_time_str}. If no follow-up is needed, use null.
   - `appointment_date_time`: If the patient booked/confirmed an appointment, extract the date/time and convert to IST (e.g., "2026-06-05 11:30:00"). Otherwise, use null.
   - `doctor`: Extract any mentioned doctor's name. Otherwise, use null.
   - `hospital_location`: Extract the preferred hospital location/center name. Otherwise, use null.
   - `sentiment_score`: Rate the user's sentiment from 0.0 (very negative/angry) to 1.0 (very positive/happy), with 0.5 as neutral.

You MUST return your response as a valid JSON object with the following schema:
{{
  "summary": "string (a single paragraph call summary)",
  "new_stage_id": integer (the selected stage ID from the list),
  "next_call_on": "string or null",
  "appointment_date_time": "string or null",
  "doctor": "string or null",
  "hospital_location": "string or null",
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
            response = await stream.collect()

            text = response.text.strip()
            if text.startswith("```"):
                first_newline = text.find("\n")
                if first_newline != -1:
                    text = text[first_newline:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            res_dict = json.loads(text)

            summary = res_dict.get("summary") or ""
            new_stage_id = res_dict.get("new_stage_id")
            next_call_on = res_dict.get("next_call_on")
            appointment_date_time = res_dict.get("appointment_date_time")
            doctor = res_dict.get("doctor")
            hospital_location = res_dict.get("hospital_location")
            sentiment_score = res_dict.get("sentiment_score", 0.5)

            if new_stage_id is not None:
                try:
                    new_stage_id = int(new_stage_id)
                except ValueError:
                    new_stage_id = fallback_stage_id
            else:
                new_stage_id = fallback_stage_id

            if not summary:
                summary = await SessionRecorder.generate_summary(llm_engine, history)

        except Exception as e:
            logger.error(
                "analyze_call failed: %s. Falling back to default heuristics.", e
            )
            summary = await SessionRecorder.generate_summary(llm_engine, history)
            new_stage_id = fallback_stage_id
            next_call_on = None
            appointment_date_time = ""
            doctor = ""
            hospital_location = ""
            sentiment_score = 0.5

        target_stage_ids = [
            sid for sid in [not_answering_id, follow_up_id] if sid is not None
        ]
        if new_stage_id is not None and new_stage_id in target_stage_ids and not next_call_on:
            tomorrow = current_time + datetime.timedelta(hours=24)
            next_call_on = tomorrow.strftime("%Y-%m-%d %H:%M:%S")

        return {
            "summary": summary,
            "new_stage_id": new_stage_id,
            "next_call_on": next_call_on,
            "appointment_date_time": appointment_date_time,
            "doctor": doctor,
            "hospital_location": hospital_location,
            "sentiment_score": sentiment_score,
        }
