
import sys
import os
import json
import asyncio
import logging
import datetime

import asyncpg
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

from mantra.utils import send_to_backend, save_call_event  # noqa: E402

logger = logging.getLogger("mantra.reconcile")
logging.basicConfig(level=logging.INFO)

# Don't touch calls still plausibly in-flight — give finalize() (and its own
# ~15s ceiling) room to finish naturally before treating something as orphaned.
GRACE_PERIOD_MINUTES = 5
# Don't chase calls forever — past this age, log and skip rather than spam
# retries against what's likely stale/irrelevant data.
MAX_AGE_HOURS = 48


async def _get_conn():
    return await asyncpg.connect(
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DB"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        timeout=10.0,
    )


ORPHAN_QUERY = """
SELECT e.call_id, e.created_at AS entrypoint_at, e.ai_call_id
FROM call_events e
WHERE e.event_type = 'entrypoint_started'
  AND e.created_at < NOW() - ($1 || ' minutes')::interval
  AND e.created_at > NOW() - ($2 || ' hours')::interval
  AND NOT EXISTS (
    SELECT 1 FROM call_events b
    WHERE b.call_id = e.call_id
      AND b.event_type IN ('backend_sent', 'backend_enriched')
  )
ORDER BY e.created_at ASC;
"""

LATEST_FAILED_QUERY = """
SELECT event_payload
FROM call_events
WHERE call_id = $1 AND event_type = 'backend_failed'
ORDER BY created_at DESC
LIMIT 1;
"""

LATEST_CHECKPOINT_QUERY = """
SELECT event_payload
FROM call_events
WHERE call_id = $1 AND event_type = 'finalize_checkpoint'
ORDER BY created_at DESC
LIMIT 1;
"""

CALL_LOG_QUERY = """
SELECT call_log, status, recording_url
FROM call_logs
WHERE call_id = $1;
"""


async def _reconstruct_payload(conn, call_id: str, entrypoint_ai_call_id=""):
    """Best available payload for this call_id, in order of preference."""
    row = await conn.fetchrow(LATEST_FAILED_QUERY, call_id)
    if row and row["event_payload"]:
        payload = row["event_payload"]
        return json.loads(payload) if isinstance(payload, str) else payload

    row = await conn.fetchrow(LATEST_CHECKPOINT_QUERY, call_id)
    if row and row["event_payload"]:
        payload = row["event_payload"]
        return json.loads(payload) if isinstance(payload, str) else payload

    row = await conn.fetchrow(CALL_LOG_QUERY, call_id)
    if row and row["call_log"]:
        try:
            data = json.loads(row["call_log"])
        except (json.JSONDecodeError, TypeError):
            data = {}
        if row["recording_url"] and not data.get("recording_url"):
            data["recording_url"] = row["recording_url"]
        event_name = "CALL_RETRY" if row["status"] in ("No Answer", "Busy", "Failed") else "CALL_DATA_UPDATE"
        return {"event": event_name, "data": data}

    # No trace of a built payload anywhere — minimal retry signal so the lead
    # isn't stuck with no record of the attempt at all.

    return {
        "event": "CALL_RETRY",
        "data": {
            "call_id": call_id,
            "call_status": "Failed",
            "ai_call_id": entrypoint_ai_call_id,
        },
    }


async def reconcile_once():
    conn = await _get_conn()
    delivered_count = 0
    failed_count = 0
    try:
        orphans = await conn.fetch(ORPHAN_QUERY, str(GRACE_PERIOD_MINUTES), str(MAX_AGE_HOURS))
        logger.info(f"Found {len(orphans)} orphaned call(s) to reconcile")

        for row in orphans:
            call_id = str(row["call_id"])
            payload = await _reconstruct_payload(conn, call_id, row.get("ai_call_id", ""))

            logger.info(f"Reconciling call_id={call_id} — event={payload.get('event')}")
            try:
                # Resilient defaults here — no 15s ceiling in this process,
                # so let it actually retry against a flaky backend.
                delivered = await send_to_backend(payload, max_retries=3, timeout_seconds=30.0)
            except Exception as e:
                logger.error(f"Reconciliation delivery raised for call_id={call_id}: {e}")
                delivered = False

            await save_call_event(
                call_id=call_id,
                event_type="backend_sent" if delivered else "backend_failed",
                event_source="reconciliation",
                event_payload=payload,
                event_status="success" if delivered else "failed",
                event_log=f"reconciled entrypoint_at={row['entrypoint_at']} delivered={delivered}",
            )

            if delivered:
                delivered_count += 1
            else:
                failed_count += 1

        logger.info(f"Reconciliation pass complete: {delivered_count} delivered, {failed_count} still failing")
        if failed_count:
            logger.warning(
                f"{failed_count} call(s) still undelivered after reconciliation — "
                f"check MANTRAASSIST_BACKEND_URL reachability / alert on this metric"
            )
    finally:
        await conn.close()

    return delivered_count, failed_count


async def run_forever(interval_seconds: int = 300):
    while True:
        try:
            await reconcile_once()
        except Exception as e:
            logger.error(f"Reconciliation pass crashed: {e}", exc_info=True)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(reconcile_once())