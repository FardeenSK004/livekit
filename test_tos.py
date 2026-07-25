import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

# Load env vars so report_telemetry can find TOS_ENDPOINT and TOS_TOKEN
load_dotenv(Path(__file__).parent / ".env.local")

from mantra.utils import report_telemetry

TOS_TASK_ID = "12255"

STEPS = [
    "webhook_received",
    "agent_dispatched",
    "sip_call_initiating",
    "sip_call_connected",
    "sip_call_failed",
    "agent_started",
    "room_connected",
    "voice_engine_initialized",
    "participant_joined",
    "call_ended",
    "post_processing_started",
    "data_sent_to_backend",
    "call_complete",
    "call_dequeued",
    "call_dispatched",
    "dispatch_failed",
]


async def main():
    print(f"TOS task ID: {TOS_TASK_ID}")
    print(f"TOS endpoint: {os.getenv('TOS_ENDPOINT', 'https://imitate-chive-ruined.ngrok-free.dev')}")
    print()

    for i, step in enumerate(STEPS, 1):
        msg = f"[test] {step}"
        ok = await report_telemetry(tos_task_id=TOS_TASK_ID, message=msg)
        status = "OK" if ok else "FAIL"
        print(f"  [{i:02d}] {step:30s} → {status}")

    print()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
