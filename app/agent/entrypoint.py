"""Voice agent entrypoint — AgentServer, rtc_session, run_agent."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import sys

# ── Suppress OpenTelemetry 429 errors ──────────────────────────────────
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
os.environ.setdefault("OTEL_TRACES_EXPORTER", "none")
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("https_proxy", None)
os.environ.pop("http_proxy", None)

from dotenv import load_dotenv
from livekit import api, rtc
from livekit.agents import (
    Agent,
    AgentServer,
    JobContext,
    cli,
    mcp as lk_mcp,
)

from app.alerter.email import send_crash_email
from app.agent.context import (
    build_initial_instructions,
    extract_kb_scope,
    resolve_inbound_context,
)
from app.agent.finalize import finalize_call
from app.agent.pipeline import (
    create_agent_session,
    create_llm,
    create_tts,
    resolve_voice_config,
)
from app.agent.safety import (
    create_call_limiter,
    create_farewell_safety_net,
    create_inactivity_monitor,
)
from app.agent.session import SessionManager
from app.agent.tools import AssistantFunctions, get_agent_tools
from app.config import settings
from app.config.logging import setup_logger
from app.recording.session_recorder import SessionRecorder
from app.services.telemetry import report_telemetry

load_dotenv()
load_dotenv(".env.local", override=True)

logger = setup_logger("app.agent.entrypoint", level=logging.DEBUG)
logging.getLogger("livekit.agents").setLevel(logging.DEBUG)
logging.getLogger("opentelemetry").setLevel(logging.ERROR)
logger.info("Initializing process...")

server = AgentServer(num_idle_processes=settings.AGENT_MAX_WORKERS)

_bg_tasks: set[asyncio.Task] = set()


def create_bg_task(coro):
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


async def force_disconnect_room(ctx: JobContext):
    """Delete the room via LiveKit API. Falls back to local disconnect."""
    try:
        lk_api = api.LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET"),
        )
        await lk_api.room.delete_room(api.DeleteRoomRequest(room=ctx.room.name))
        await lk_api.aclose()
    except Exception as e:
        logger.error("Failed to delete room via API: %s", e)
        try:
            await ctx.room.disconnect()
        except Exception as e2:
            logger.error("Local disconnect also failed: %s", e2)


@server.rtc_session(agent_name="mantra-agent")
async def entrypoint(ctx: JobContext):
    entrypoint_start_time = asyncio.get_event_loop().time()
    _effective_call_metadata: dict = {}

    logger.info("Entrypoint reached for room: %s", ctx.room.name)
    await ctx.connect()

    logger.info("--- Starting agent session ---")
    logger.info("Room: %s", ctx.room.name)
    logger.info("Job ID: %s", ctx.job.id)
    logger.info("Metadata: %s", ctx.job.metadata)

    kb_ids_list: list[str] = []
    kb_tags_list: list[str] = []
    resolved_context = None
    meta_payload: dict = {}

    if ctx.job.metadata:
        try:
            meta_payload = json.loads(ctx.job.metadata)

            if meta_payload.get("direction") == "inbound":
                phone_number = meta_payload.get("phone_number", "")
                if phone_number:
                    resolved_context = await resolve_inbound_context(phone_number)
                    if resolved_context is None:
                        logger.error(
                            "Cannot resolve inbound call context for %s. "
                            "Rejecting call — MantraAssist is unreachable.",
                            phone_number,
                        )
                        try:
                            await ctx.room.disconnect()
                        except Exception:
                            pass
                        return

                    meta_payload.update(resolved_context)
                    logger.info(
                        "Merged inbound context into metadata for org_id=%s",
                        resolved_context.get("org_id"),
                    )
                else:
                    logger.warning(
                        "Inbound call has no phone_number in metadata — cannot resolve context"
                    )

            kb_ids_list, kb_tags_list = extract_kb_scope(meta_payload)
        except Exception as e:
            logger.error("Failed to parse/resolve metadata: %s", e)

    logger.info("KB scope: kb_ids=%s, kb_tags=%s", kb_ids_list, kb_tags_list)

    session_mgr = SessionManager(call_id=ctx.job.id, room_name=ctx.room.name)
    call_state = session_mgr.call_state

    call_state["agent_joined_at"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    call_state["human_joined_at"] = None
    call_state["call_initiated_at"] = None

    tos_task_id = None
    call_id = ctx.job.id
    if ctx.job.metadata:
        try:
            payload = json.loads(ctx.job.metadata)
            _effective_call_metadata = dict(payload)
            call_id = payload.get("call_id") or payload.get("voice_id") or ctx.job.id
            tos_task_id = payload.get("tos_task_id") or payload.get("metadata", {}).get("tos_task_id")
            metadata = payload.get("metadata", {})
            if isinstance(metadata, dict):
                call_state["call_initiated_at"] = metadata.get("call_initiated_at")
        except Exception:
            pass

    call_state["tos_task_id"] = tos_task_id
    call_state["call_id"] = str(call_id)

    await _register_inbound_call_in_redis(ctx, call_id)

    recorder = SessionRecorder()

    async def _telemetry(status: str, detail: str = "", data: dict | None = None, wait: bool = False):
        _tos_task_id = call_state.get("tos_task_id")
        _cid = call_state.get("call_id")
        if _tos_task_id:
            msg = f"[Agent Worker] {status}"
            if detail:
                msg += f" — {detail}"
            if wait:
                await report_telemetry(tos_task_id=_tos_task_id, message=msg, call_id=_cid, data=data)
            else:
                create_bg_task(report_telemetry(tos_task_id=_tos_task_id, message=msg, call_id=_cid, data=data))

    await _telemetry("agent_started", f"room={ctx.room.name}")
    await _telemetry("room_connected", f"room={ctx.room.name}")

    fnc_ctx = AssistantFunctions(
        ctx.job.metadata,
        ctx.room.name,
        ctx=ctx,
        kb_ids=kb_ids_list,
        kb_tags=kb_tags_list,
        create_bg_task=create_bg_task,
        force_disconnect=lambda: force_disconnect_room(ctx),
    )

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            recorder.start_recording(track, f"participant_{participant.identity}")

    @ctx.room.on("local_track_published")
    def on_local_track_published(
        publication: rtc.LocalTrackPublication, track: rtc.Track
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            recorder.start_recording(track, "agent")

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        session_mgr.append_timeline("Remote Participant Disconnected")
        logger.info(
            "Participant %s disconnected. Force-ending call.", participant.identity
        )
        create_bg_task(force_disconnect_room(ctx))

    client_name = "User"
    is_inbound = False
    payload: dict = {}

    if ctx.job.metadata:
        try:
            if resolved_context is not None:
                payload = dict(meta_payload)
            else:
                payload = json.loads(ctx.job.metadata)
            _effective_call_metadata = dict(payload)

            if payload.get("direction") == "inbound":
                is_inbound = True

            initial_instructions, client_name = build_initial_instructions(
                payload,
                is_inbound=is_inbound,
                resolved_context=resolved_context,
            )
            logger.info(
                "Loaded full context for %s (inbound: %s)", client_name, is_inbound
            )
        except Exception as e:
            logger.error("Failed to parse metadata: %s", e)
            initial_instructions, client_name = build_initial_instructions(
                {}, is_inbound=False
            )
    else:
        initial_instructions, client_name = build_initial_instructions(
            {}, is_inbound=False
        )

    voice_input, voice_id, voice_speed = resolve_voice_config(payload if payload else {})
    model_name = payload.get("model", "openai") if payload else "openai"
    ai_payload = payload.get("ai_payload") if payload else {}
    if isinstance(ai_payload, dict) and ai_payload.get("ai_model"):
        model_name = ai_payload["ai_model"]

    logger.info("--- CALL CONFIGURATION ---")
    logger.info("Model: %s", model_name)
    logger.info("Voice: %s (ID: %s)", voice_input, voice_id)
    logger.info("Speed: %s", voice_speed)
    logger.info("--------------------------")

    llm_engine = create_llm(payload if payload else {})
    tts_engine = create_tts(voice_id, voice_speed, language="en")
    session = create_agent_session(llm_engine, tts_engine)

    await _telemetry("Agent voice engine ready", f"model={model_name}")

    try:
        mcp_server = lk_mcp.CstdioServerParameters(
            command="uv",
            args=["run", "python", "mcp/server.py"],
        )
        mcp_client = lk_mcp.McpClient(mcp_server)
        await mcp_client.start()
        logger.info("Connected to local MCP database server")
        agent_tools = get_agent_tools(fnc_ctx)
        agent_tools.append(mcp_client.create_tool_context())
    except Exception as e:
        logger.error("Failed to start MCP server: %s", e)
        agent_tools = get_agent_tools(fnc_ctx)

    agent = Agent(instructions=initial_instructions, tools=agent_tools)
    fnc_ctx.agent = agent
    fnc_ctx.session = session

    @session.on("agent_state_changed")
    def on_agent_state(ev):
        call_state["agent_state"] = ev.new_state
        if getattr(ev, "old_state", None) == "speaking" and ev.new_state != "speaking":
            call_state["last_activity"] = asyncio.get_event_loop().time()

    @session.on("user_state_changed")
    def on_user_state(ev):
        if ev.new_state == "speaking":
            call_state["last_activity"] = asyncio.get_event_loop().time()
            call_state["prompted_inactivity"] = False

    limiter_task = None
    inactivity_task = None
    safety_net_task = None

    try:
        await session.start(agent=agent, room=ctx.room)

        disconnect = lambda: force_disconnect_room(ctx)

        inactivity_task = asyncio.create_task(
            create_inactivity_monitor(
                ctx,
                session,
                call_state,
                disconnect,
                create_bg_task,
            )()
        )
        limiter_task = asyncio.create_task(
            create_call_limiter(
                ctx,
                session,
                agent,
                call_state,
                entrypoint_start_time,
                disconnect,
                create_bg_task,
            )()
        )
        safety_net_task = asyncio.create_task(
            create_farewell_safety_net(ctx, session, call_state, disconnect)()
        )

        for publication in ctx.room.local_participant.track_publications.values():
            if publication.track and publication.track.kind == rtc.TrackKind.KIND_AUDIO:
                recorder.start_recording(publication.track, "agent")

        for participant in ctx.room.remote_participants.values():
            for publication in participant.track_publications.values():
                if (
                    publication.track
                    and publication.track.kind == rtc.TrackKind.KIND_AUDIO
                ):
                    recorder.start_recording(
                        publication.track, f"participant_{participant.identity}"
                    )

        if ctx.room.name.startswith("test_"):
            logger.info(
                "Test room detected. Skipping wait for remote participant."
            )
            call_state["user_joined"] = True
        else:
            logger.info("Waiting for remote participant to join...")
            wait_start = asyncio.get_event_loop().time()
            while not list(ctx.room.remote_participants.values()):
                await asyncio.sleep(0.5)
                if asyncio.get_event_loop().time() - wait_start > 60.0:
                    logger.warning(
                        "Remote participant did not join within 60 seconds. Disconnecting."
                    )
                    await force_disconnect_room(ctx)
                    return

            logger.info("Remote participant joined. Initializing conversation...")
            call_state["user_joined"] = True
            call_state["human_joined_at"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            session_mgr.append_timeline("Remote Participant Joined")
            await _telemetry("Customer joined the call")
            await asyncio.sleep(0.5)

        logger.info("Generating greeting for %s...", client_name)
        try:
            if is_inbound:
                session.generate_reply(
                    instructions=(
                        "Initiate the conversation according to your system prompt. "
                        "Introduce yourself and ask how you can help."
                    )
                )
            else:
                session.generate_reply(
                    instructions=(
                        f"Greet the user named {client_name} and follow the opening "
                        "script in your instructions."
                    )
                )
            logger.info("Greeting generation requested.")
        except RuntimeError as e:
            logger.warning("Could not generate greeting (session may be closed): %s", e)

        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1.0)

    except asyncio.CancelledError:
        logger.info("Call entrypoint coroutine cancelled.")
    except Exception as e:
        logger.error("Error in entrypoint execution: %s", e, exc_info=True)
        context_data = {
            "Room Name": getattr(ctx.room, "name", "N/A"),
            "Job ID": getattr(ctx.job, "id", "N/A"),
            "Process ID (PID)": os.getpid(),
        }
        try:
            if ctx.job.metadata:
                context_data["Job metadata"] = ctx.job.metadata
        except Exception:
            pass
        try:
            await send_crash_email(
                service_name="Livekit Voice Agent worker",
                error=e,
                context_data=context_data,
            )
        except Exception as email_err:
            logger.error("Failed to dispatch crash email: %s", email_err)
    finally:
        logger.info("Entering entrypoint finally block (cleaning up and finalizing)...")

        for task in (limiter_task, inactivity_task, safety_net_task):
            if task and not task.done():
                task.cancel()

        history_snapshot = (
            list(session.history.messages()) if (session and session.history) else []
        )

        async def finalize():
            await finalize_call(
                ctx=ctx,
                call_state=call_state,
                history_snapshot=history_snapshot,
                recorder=recorder,
                llm_engine=llm_engine,
                effective_call_metadata=_effective_call_metadata,
                entrypoint_start_time=entrypoint_start_time,
            )

        await asyncio.shield(finalize())


async def _register_inbound_call_in_redis(ctx: JobContext, call_id: str) -> None:
    """Track inbound calls in Redis for capacity enforcement."""
    try:
        import redis.asyncio as redis

        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        is_tracked = await r.hexists("calls:active", call_id)
        if not is_tracked:
            max_concurrency = settings.effective_max_concurrency
            active_count = await r.hlen("calls:active")
            if active_count >= max_concurrency:
                logger.warning(
                    "Capacity full (%s/%s). Rejecting inbound call %s.",
                    active_count,
                    max_concurrency,
                    call_id,
                )
                await r.aclose()
                await ctx.room.disconnect()
                return
            await r.hset("calls:active", call_id, ctx.room.name)
            await r.set(f"calls:status:{call_id}", "in_progress_inbound")
            logger.info("Registered inbound call %s in Redis calls:active", call_id)
        await r.aclose()
    except Exception as e:
        logger.error("Failed to register active call in Redis: %s", e)


def run_agent():
    _is_start_cmd = "start" in sys.argv
    if _is_start_cmd:
        logger.info("Mantra Agent Server is starting...")

    try:
        cli.run_app(server)
    except Exception as e:
        logger.error("Failed to run agent server: %s", e, exc_info=True)
        try:
            asyncio.run(
                send_crash_email(
                    service_name="Livekit Voice Agent Worker (Core/Startup)",
                    error=e,
                    context_data={
                        "Status": "Crashloop / Process Death",
                        "PID": os.getpid(),
                    },
                )
            )
        except Exception as email_err:
            logger.error("Failed to dispatch core crash email: %s", email_err)
        raise


if __name__ == "__main__":
    run_agent()
