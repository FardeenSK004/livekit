"""S3 recording storage service."""

from __future__ import annotations

import logging
import os
from typing import Optional

import boto3

from app.config import settings

logger = logging.getLogger("app.services.s3")


class S3Service:
    def __init__(self):
        self._client = None

    def start(self):
        bucket = settings.s3_bucket
        if not bucket:
            logger.info("S3 bucket not configured — recording upload disabled")
            return
        self._client = self._build_client()

    def _build_client(self):
        # Strip proxy env vars so requests/urllib3 doesn't pick them up
        saved = {}
        for var in (
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "https_proxy",
            "http_proxy",
            "PLIVO_PROXY",
        ):
            val = os.environ.pop(var, None)
            if val is not None:
                saved[var] = val
        try:
            kwargs = {"region_name": settings.AWS_REGION}
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
            return boto3.client("s3", **kwargs)
        finally:
            os.environ.update(saved)

    @property
    def enabled(self) -> bool:
        return self._client is not None and bool(settings.s3_bucket)

    def upload_bytes(self, file_bytes: bytes, s3_key: str) -> Optional[str]:
        """Synchronous upload matching mantra.utils.upload_to_s3."""
        bucket = settings.s3_bucket
        if not bucket:
            logger.warning("AWS_S3_BUCKET_NAME not set — skipping upload")
            return None
        if self._client is None:
            self.start()
        if not self.enabled:
            return None
        try:
            self._client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=file_bytes,
                ContentType="audio/mpeg",
                ACL="public-read",
            )
            url = f"https://{bucket}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
            logger.info("Uploaded recording to S3: %s", url)
            return url
        except Exception as e:
            logger.error("S3 upload failed: %s", e, exc_info=True)
            return None

    async def upload_recording(
        self, call_id: str, audio_bytes: bytes, content_type: str = "audio/mpeg"
    ) -> Optional[str]:
        del content_type  # put_object uses audio/mpeg
        return self.upload_bytes(audio_bytes, f"recordings/{call_id}.mp3")


s3_service = S3Service()
