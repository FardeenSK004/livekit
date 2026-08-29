"""Timeout constants for telephony, HTTP, and background tasks."""

from typing import Final

HTTP_CONNECT_TIMEOUT_SECONDS: Final[float] = 15.0
HTTP_READ_TIMEOUT_SECONDS: Final[float] = 60.0
HTTP_WRITE_TIMEOUT_SECONDS: Final[float] = 15.0
HTTP_POOL_TIMEOUT_SECONDS: Final[float] = 15.0

POST_CALL_ANALYSIS_TIMEOUT_SECONDS: Final[float] = 70.0
POST_CALL_SUMMARY_TIMEOUT_SECONDS: Final[float] = 45.0
S3_UPLOAD_TIMEOUT_SECONDS: Final[float] = 10.0

INACTIVITY_NUDGE_SECONDS: Final[float] = 15.0
INACTIVITY_DISCONNECT_SECONDS: Final[float] = 30.0

FAREWELL_WARNING_SECONDS: Final[float] = 150.0  # 2m30s
MAX_CALL_DURATION_SECONDS: Final[float] = 180.0  # 3m00s hard kill

ENTRYPOINT_SHUTDOWN_TIMEOUT_SECONDS: Final[float] = 40.0
