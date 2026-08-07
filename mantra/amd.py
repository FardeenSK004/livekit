"""Answering Machine Detection (AMD) helpers.

Wraps LiveKit's ``AMD`` detector behind a small, typed interface so call logic
stays free of detector plumbing. Detection runs on the first utterance of the
target participant (outbound SIP callers). Any failure degrades to "human" so
the conversation proceeds normally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from livekit.agents import AMD, AMDCategory

logger = logging.getLogger("mantra.amd")


@dataclass(frozen=True)
class VoicemailDetection:
    """Outcome of answering-machine detection."""

    detected: bool
    category: Optional[str] = None
    transcript: str = ""

    @classmethod
    def from_prediction(cls, prediction) -> "VoicemailDetection":
        machine_categories = (
            AMDCategory.MACHINE_VM,
            AMDCategory.MACHINE_UNAVAILABLE,
        )
        return cls(
            detected=prediction.category in machine_categories,
            category=prediction.category.value if prediction.category else None,
            transcript=prediction.transcript or "",
        )


async def detect_voicemail(
    session,
    participant_identity: str,
    *,
    interrupt_on_machine: bool = True,
) -> VoicemailDetection:
    """Detect whether ``participant_identity`` is an answering machine.

    Args:
        session: The agent session running the call.
        participant_identity: Identity of the SIP participant to classify.
        interrupt_on_machine: Stop the machine's greeting once detected.

    Returns:
        A :class:`VoicemailDetection`. On any failure a non-detected result is
        returned so the call is treated as a human answer.
    """
    try:
        async with AMD(
            session,
            participant_identity=participant_identity,
            ivr_detection=False,
            interrupt_on_machine=interrupt_on_machine,
        ) as amd:
            prediction = await amd.execute()
        result = VoicemailDetection.from_prediction(prediction)
        logger.info(
            "AMD result: detected=%s category=%s reason=%s transcript=%s",
            result.detected,
            result.category,
            getattr(prediction, "reason", None),
            result.transcript[:120],
        )
        return result
    except Exception:
        logger.exception("AMD failed — proceeding as human")
        return VoicemailDetection(detected=False)
