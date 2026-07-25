"""Safety monitors — inactivity, farewell net, call duration limits."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Callable, Optional

from livekit import rtc
from livekit.agents import Agent, AgentSession, JobContext

from app.config.constants import FAREWELL_PHRASES

logger = logging.getLogger("app.agent.safety")


def is_farewell(text: str) -> bool:
    """Return True if *text* contains a known farewell phrase."""
    lower = (text or "").lower().strip()
    return any(phrase in lower for phrase in FAREWELL_PHRASES)


class SafetyMonitor:
    """Thin helper class for unit tests and external callers."""

    @staticmethod
    def is_farewell(text: str) -> bool:
        return is_farewell(text)


def create_inactivity_monitor(
    ctx: JobContext,
    session: AgentSession,
    call_state: dict,
    force_disconnect: Callable,
    create_bg_task: Callable,
):
    """Return coroutine that monitors user inactivity (5s prompt / 10s disconnect)."""

    async def inactivity_monitor():
        logger.info("Inactivity monitor started.")
        while not call_state.get("user_joined"):
            await asyncio.sleep(1.0)

        call_state["last_activity"] = asyncio.get_event_loop().time()
        call_state["prompted_inactivity"] = False

        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1.0)
            now = asyncio.get_event_loop().time()
            agent_state = call_state.get("agent_state", "initializing")
            last_activity = call_state.get("last_activity", now)
            time_since_activity = now - last_activity

            if agent_state in ["listening", "idle"]:
                if time_since_activity > 10.0:
                    call_state["timeline"].append(
                        {
                            "event": "Inactivity Timeout Disconnect",
                            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                        }
                    )
                    create_bg_task(force_disconnect())
                    break
                if time_since_activity > 5.0 and not call_state.get(
                    "prompted_inactivity", False
                ):
                    logger.info("No response for 5s. Prompting user...")
                    call_state["prompted_inactivity"] = True
                    try:
                        session.generate_reply(
                            user_input="[System: The user has been silent. Briefly ask if they are still there (e.g. 'Are you still there?' or 'Hello?'). Keep it extremely short.]"
                        )
                    except RuntimeError as e:
                        logger.warning(
                            "Failed to generate inactivity reply (session may be closing): %s",
                            e,
                        )
                    except Exception as e:
                        logger.error(
                            "Unexpected error generating inactivity reply: %s", e
                        )

    return inactivity_monitor


def create_farewell_safety_net(
    ctx: JobContext,
    session: AgentSession,
    call_state: dict,
    force_disconnect: Callable,
):
    """Return coroutine that disconnects if agent says goodbye without end_call."""

    async def farewell_safety_net():
        await asyncio.sleep(10.0)
        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(3.0)
            if not (session and hasattr(session, "history") and session.history):
                continue
            try:
                messages = list(session.history.messages())
                if not messages:
                    continue
                last_msg = messages[-1]
                role = getattr(last_msg, "role", "")
                content = str(getattr(last_msg, "content", "")).lower()
                if role == "assistant" and any(
                    phrase in content for phrase in FAREWELL_PHRASES
                ):
                    logger.warning(
                        "Safety net: Agent said goodbye but end_call was never invoked. Force disconnecting."
                    )
                    call_state["timeline"].append(
                        {
                            "event": "Farewell Safety Net Triggered",
                            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                        }
                    )
                    await asyncio.sleep(3.0)
                    await force_disconnect()
                    break
            except Exception as e:
                logger.debug("Farewell safety net error: %s", e)

    return farewell_safety_net


def create_call_limiter(
    ctx: JobContext,
    session: AgentSession,
    agent: Agent,
    call_state: dict,
    entrypoint_start_time: float,
    force_disconnect: Callable,
    create_bg_task: Callable,
):
    """Return coroutine enforcing 150s farewell / 180s hard disconnect."""

    async def call_limiter():
        logger.info("Call limiter started — waiting for remote participant to join.")
        force_disconnect_cancelled = asyncio.Event()
        try:
            while not list(ctx.room.remote_participants.values()):
                await asyncio.sleep(1.0)

            logger.info("Remote participant detected in room.")
            elapsed = asyncio.get_event_loop().time() - entrypoint_start_time
            logger.info(
                "Participant joined at t=%.2fs. Farewell reply in %.2fs, hard kill in %.2fs.",
                elapsed,
                max(0.0, 150.0 - elapsed),
                max(0.0, 180.0 - elapsed),
            )

            async def force_disconnect_timer():
                try:
                    disconnect_delay = max(
                        0.0,
                        180.0
                        - (
                            asyncio.get_event_loop().time() - entrypoint_start_time
                        ),
                    )
                    logger.info(
                        "Force-disconnect timer armed: t+%.2fs", disconnect_delay
                    )
                    await asyncio.wait_for(
                        force_disconnect_cancelled.wait(), timeout=disconnect_delay
                    )
                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    logger.info("Force-disconnect timer cancelled.")
                    return
                else:
                    logger.info(
                        "Call ended naturally — force-disconnect timer exiting."
                    )
                    return

                if ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
                    logger.warning(
                        "HARD DISCONNECT: 3m limit reached. Force disconnecting room."
                    )
                    call_state["timeline"].append(
                        {
                            "event": "Max Call Duration Reached",
                            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                        }
                    )
                    await force_disconnect()
                else:
                    logger.info(
                        "Room already disconnected — force-disconnect skipping."
                    )

            create_bg_task(force_disconnect_timer())

            stage1_delay = max(
                0.0,
                150.0 - (asyncio.get_event_loop().time() - entrypoint_start_time),
            )
            await asyncio.sleep(stage1_delay)
            elapsed = asyncio.get_event_loop().time() - entrypoint_start_time
            logger.info("Farewell stage hit at t=%.2fs", elapsed)

            if ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
                logger.info("Updating agent instructions for farewell.")
                current_inst = agent.instructions
                if isinstance(current_inst, str):
                    farewell_inst = (
                        "IMPORTANT: The call time is ending now. "
                        "On your next turn, say a quick, natural one-sentence goodbye "
                        "and do not continue the conversation. Do not ask questions."
                    )
                    await agent.update_instructions(
                        current_inst + "\n\n" + farewell_inst
                    )
                logger.info("Farewell instructions set.")

                try:
                    logger.info("Waiting for session to become inactive (25s timeout).")
                    await asyncio.wait_for(session.wait_for_inactive(), timeout=25.0)
                    logger.info("Session became inactive naturally.")
                except asyncio.TimeoutError:
                    logger.warning(
                        "Session did not go inactive within 25s — force-disconnect at 3m will handle it."
                    )
            else:
                logger.warning("Room already disconnected — skipping farewell.")
        except asyncio.CancelledError:
            logger.info("Call limiter cancelled (call ended naturally before limits).")
            try:
                force_disconnect_cancelled.set()
            except Exception:
                pass
        except Exception as e:
            logger.error("Error in call limiter: %s", e)

    return call_limiter
