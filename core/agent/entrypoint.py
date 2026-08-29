"""
LiveKit Voice Agent Entrypoint.
Connects audio streams, initializes LLM/STT/TTS plugins, starts monitors, and orchestrates the call lifecycle.
"""

import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    inference,
    llm,
)
from livekit.agents import TurnHandlingOptions
from livekit.plugins import silero

from core.language_manager import LanguageManager
from core.agent.tools import AssistantFunctions
from core.agent.context_resolver import resolve_inbound_context, get_global_kb
from core.agent.pipeline_factory import (
    build_live_llm,
    build_stt,
    build_tts,
    build_vad,
    resolve_voice_id,
)
from core.agent.monitors import (
    register_session_lifecycle_listeners,
    start_transcript_logger,
    start_inactivity_monitor,
    start_call_limiter,
)
from core.agent.finalizer import finalize_call
from services.session_recorder import SessionRecorder

logger = logging.getLogger("core.agent")
AGENT_NAME = os.getenv("AGENT_NAME", "mantra-agent")

server = AgentServer(num_idle_processes=20, shutdown_process_timeout=120.0)


def prewarm(proc: JobProcess):
    """Preload VAD neural model to optimize cold start latency."""
    proc.userdata["vad"] = silero.VAD.load(
        min_speech_duration=0.10,
        min_silence_duration=0.25,
        prefix_padding_duration=0.20,
    )


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext):
    """Main worker entry point invoked per LiveKit voice room session."""
    logger.info(f"Connecting to room: {ctx.room.name} (Job: {ctx.job.id})")
    await ctx.connect()

    # 1. Parse metadata and resolve inbound/outbound context
    raw_metadata = ctx.job.metadata or "{}"
    try:
        call_payload = json.loads(raw_metadata) if raw_metadata else {}
    except Exception:
        call_payload = {}

    is_inbound = call_payload.get("direction") == "inbound" or ctx.room.name.startswith("inbound_")
    if is_inbound:
        dialed_number = call_payload.get("called_number") or call_payload.get("sip_call_to") or ""
        resolved = await resolve_inbound_context(dialed_number)
        if resolved:
            call_payload.update({k: v for k, v in resolved.items() if v is not None})

    ai_p = call_payload.get("ai_payload") or {}
    voice_input = call_payload.get("voice") or ai_p.get("voice_id") or "arushi"
    voice_speed = call_payload.get("voice_speed") or ai_p.get("voice_speed") or 1.0
    model_name = call_payload.get("model") or ai_p.get("ai_model") or "deepseek"
    current_lang = (
        call_payload.get("language")
        or call_payload.get("lang")
        or ai_p.get("language")
        or ai_p.get("lang")
        or "en"
    )

    # 2. Setup call state and in-memory session recorder
    call_state = {
        "user_joined": is_inbound,
        "user_has_spoken": False,
        "initial_greeting_done": False,
        "current_language": current_lang,
        "duration": 0,
    }
    recorder = SessionRecorder()

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            recorder.start_recording(track, f"participant_{participant.identity}")

    # 3. Setup language manager & plugins (DeepSeek LLM + Cartesia Sonic-3 TTS)
    language_mgr = LanguageManager(initial_language=current_lang)
    stt_engine = build_stt(language=current_lang)
    tts_engine = build_tts(
        voice=voice_input,
        speed=float(voice_speed),
        language=current_lang,
    )
    live_llm = build_live_llm(model_preference=model_name)

    # 4. Setup Agent Tools
    fnc_ctx = AssistantFunctions(
        job_metadata=raw_metadata,
        room_name=ctx.room.name,
        ctx=ctx,
        kb_ids=call_payload.get("kb_ids"),
        kb_tags=call_payload.get("kb_tags"),
        call_state=call_state,
    )
    await fnc_ctx.warmup()

    # 5. Build Agent Instructions
    custom_prompt = call_payload.get("prompt") or call_payload.get("custom_prompt") or (
        "You are a helpful AI voice assistant. Answer the caller's questions accurately and concisely."
    )
    prompt_with_lang = f"{custom_prompt}\n\n<!-- LANGUAGE_DIRECTIVE_START -->\n{language_mgr.get_prompt_directive()}\n<!-- LANGUAGE_DIRECTIVE_END -->"

    agent = Agent(
        instructions=prompt_with_lang,
        tools=[fnc_ctx.search_knowledge_base, fnc_ctx.end_call],
    )

    # 6. Initialize Voice Session
    session = AgentSession(
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            endpointing={
                "mode": "fixed",
                "min_delay": 0.25,
                "max_delay": 1.50,
            },
            interruption={
                "mode": "adaptive",
                "min_words": 2,
                "min_duration": 0.40,
                "resume_false_interruption": True,
                "false_interruption_timeout": 1.5,
                "backchannel_boundary": (1.0, 1.0),
            },
            preemptive_generation={
                "preemptive_tts": True,
            },
        ),
        vad=ctx.proc.userdata.get("vad") or build_vad(),
        stt=stt_engine,
        llm=live_llm,
        tts=tts_engine,
    )
    fnc_ctx.session = session
    fnc_ctx.agent = agent

    # 7. Register Monitors & Event Listeners
    voice_id_str = resolve_voice_id(voice_input)
    register_session_lifecycle_listeners(session, ctx, call_state)
    start_transcript_logger(
        ctx, session, call_state, language_mgr, stt_engine, tts_engine, agent, voice_id_str
    )
    start_inactivity_monitor(ctx, session, call_state)
    start_call_limiter(ctx, call_state, max_seconds=600)

    # 8. Start Session in Room with Agent
    await session.start(agent=agent, room=ctx.room)

    # Record agent local audio tracks
    if ctx.room.local_participant:
        for publication in ctx.room.local_participant.track_publications.values():
            if publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                recorder.start_recording(publication.track, "agent")

    # 9. Register room disconnect cleanup & finalization
    @ctx.room.on("disconnected")
    def on_disconnected():
        history_snapshot = list(session.history.messages()) if hasattr(session, "history") else []
        asyncio.create_task(
            finalize_call(
                ctx=ctx,
                recorder=recorder,
                call_state=call_state,
                effective_metadata=call_payload,
                fnc_ctx=fnc_ctx,
                history_snapshot=history_snapshot,
            )
        )

    # 10. Wait for Remote Participant (Outbound Call)
    if not is_inbound:
        logger.info("Outbound call: waiting for remote participant to join room...")
        wait_start = asyncio.get_event_loop().time()
        while len(ctx.room.remote_participants) == 0:
            await asyncio.sleep(0.1)
            if not ctx.room.isconnected():
                return
            if asyncio.get_event_loop().time() - wait_start > 60.0:
                logger.warning("Remote participant did not join within 60s. Disconnecting.")
                await ctx.room.disconnect()
                return
        logger.info(f"Remote participant joined: {[p.identity for p in ctx.room.remote_participants.values()]}")
        call_state["user_joined"] = True

    # 11. Generate Initial Greeting
    await asyncio.sleep(0.1)
    client_name = call_payload.get("client_name") or "User"
    logger.info(f"Generating initial greeting for {client_name} (inbound={is_inbound})...")
    try:
        if is_inbound:
            session.generate_reply(
                instructions="Initiate the conversation according to your system prompt. Introduce yourself and ask how you can help."
            )
        else:
            session.generate_reply(
                instructions=f"Greet the user named {client_name} and follow the opening script in your instructions."
            )
    except Exception as e:
        logger.warning(f"Could not generate initial greeting: {e}")

    # 12. Main Agent Execution Loop (block until call ends)
    while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
        await asyncio.sleep(1.0)


def run_agent():
    """CLI launcher for LiveKit voice agent."""
    cli.run_app(server)


if __name__ == "__main__":
    run_agent()
