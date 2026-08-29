"""Event constants for telephony webhooks and metrics."""

from typing import Final

EVENT_CALL_DATA_UPDATE: Final[str] = "CALL_DATA_UPDATE"
EVENT_CALL_DATA_INBOUND_UPDATE: Final[str] = "CALL_DATA_INBOUND_UPDATE"
EVENT_CALL_RETRY: Final[str] = "CALL_RETRY"

STATUS_COMPLETED: Final[str] = "Completed"
STATUS_INCOMPLETE: Final[str] = "Incomplete"
STATUS_BUSY: Final[str] = "Busy"
STATUS_NO_ANSWER: Final[str] = "No Answer"
STATUS_FAILED: Final[str] = "Failed"
STATUS_IGNORED: Final[str] = "Ignored"

DIRECTION_INBOUND: Final[str] = "inbound"
DIRECTION_OUTBOUND: Final[str] = "outbound"
