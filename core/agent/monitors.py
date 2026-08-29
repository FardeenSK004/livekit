"""Call monitoring routines: inactivity timeouts, duration limits, farewell safety nets."""

import os
import asyncio
import logging
from datetime import datetime
from livekit import rtc
from helpers.alerts import send_crash_email

logger = logging.getLogger("core.agent.monitors")
AGENT_NAME = os.getenv("AGENT_NAME", "mantra-agent")


def register_session_lifecycle_listeners(session, ctx, call_state: dict):
    """Register event listeners for agent state, user speech, and errors."""

    @session.on("agent_state_changed")
    def on_agent_state(ev):
        call_state["agent_state"] = ev.new_state
        if ev.new_state == "speaking":
            call_state["greeting_started"] = True
        elif getattr(ev, "old_state", None) == "speaking" and ev.new_state != "speaking":
            call_state["last_activity"] = asyncio.get_event_loop().time()
            if call_state.get("greeting_started"):
                call_state["initial_greeting_done"] = True

    @session.on("user_state_changed")
    def on_user_state(ev):
        if ev.new_state == "speaking":
            call_state["last_activity"] = asyncio.get_event_loop().time()
            call_state["prompted_inactivity"] = False
            call_state["user_has_spoken"] = True

    @session.on("error")
    def on_session_error(ev):
        err = getattr(ev, "error", None)
        inner = err if isinstance(err, BaseException) else getattr(err, "error", None) or err
        logger.error(f"[DIAG] Pipeline error: {inner}")


def start_transcript_logger(
    ctx, session, call_state: dict, language_mgr, stt_engine, tts_engine, agent, voice_id: str
):
    """Monitor conversation transcript and handle multilingual speech switching."""
    last_size = 0

    async def _logger_loop():
        nonlocal last_size
        await asyncio.sleep(2.0)
        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            try:
                if session and hasattr(session, "history") and session.history:
                    msgs = list(session.history.messages())
                    if len(msgs) > last_size:
                        new_msgs = msgs[last_size:]
                        last_size = len(msgs)
                        for m in new_msgs:
                            role = m.role.name if hasattr(m.role, "name") else str(m.role)
                            content = " ".join([str(c) for c in m.content]) if isinstance(m.content, list) else str(m.content)
                            if content and not content.startswith("[System:"):
                                preview = content[:200] + ("..." if len(content) > 200 else "")
                                logger.info(f"[DIAG] TRANSCRIPT | {role}: {preview}")

                                if str(role).lower() in ["user", "caller"]:
                                    new_lang, switched = language_mgr.process_user_utterance(content)
                                    if switched:
                                        call_state["current_language"] = new_lang
                                        logger.info(f"[LANG] Language switched to: {new_lang}")
                                        try:
                                            stt_engine.update_options(language=new_lang)
                                            tts_engine.update_options(language=new_lang, voice=voice_id)
                                        except Exception as err:
                                            logger.warning(f"[LANG] Failed updating STT/TTS options: {err}")
            except Exception as e:
                logger.debug(f"Transcript logger error: {e}")
            await asyncio.sleep(0.4)

    return asyncio.create_task(_logger_loop())


def start_inactivity_monitor(ctx, session, call_state: dict):
    """Nudge inactive caller and disconnect after prolonged silence."""

    async def _inactivity_loop():
        while not call_state.get("user_joined"):
            await asyncio.sleep(1.0)

        call_state["last_activity"] = asyncio.get_event_loop().time()
        call_state["prompted_inactivity"] = False

        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1.0)
            if not call_state.get("initial_greeting_done"):
                call_state["last_activity"] = asyncio.get_event_loop().time()
                continue

            now = asyncio.get_event_loop().time()
            agent_state = call_state.get("agent_state", "initializing")
            last_activity = call_state.get("last_activity", now)
            elapsed = now - last_activity

            if agent_state in ["listening", "idle"]:
                if elapsed > 30.0:
                    logger.warning("Inactivity timeout: disconnecting room after 30s silence.")
                    if ctx.room:
                        await ctx.room.disconnect()
                    break
                elif elapsed > 15.0 and not call_state.get("prompted_inactivity", False):
                    call_state["prompted_inactivity"] = True
                    try:
                        session.generate_reply(
                            user_input="[System: The user has been silent. Politely ask if they are still there.]"
                        )
                    except Exception as e:
                        logger.warning(f"Inactivity nudge failed: {e}")

    return asyncio.create_task(_inactivity_loop())


def start_call_limiter(ctx, call_state: dict, max_seconds: int = 600):
    """Enforce strict hard timeout per call session."""

    async def _limiter_loop():
        await asyncio.sleep(max_seconds)
        if ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            logger.warning(f"Hard call duration limit reached ({max_seconds}s). Disconnecting.")
            if ctx.room:
                await ctx.room.disconnect()

    return asyncio.create_task(_limiter_loop())
