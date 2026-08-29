"""AWS S3 audio recording upload helper."""

import logging
import os
from typing import Optional
import boto3

logger = logging.getLogger("mantra.helpers.s3")


def upload_to_s3(file_bytes: bytes, s3_key: str) -> Optional[str]:
    """Upload audio bytes to S3 and return public URL."""
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    region = os.getenv("AWS_REGION", "us-east-1")

    if not bucket_name:
        logger.warning("AWS_S3_BUCKET_NAME not set — skipping upload")
        return None

    # Strip proxy env vars so requests/urllib3 doesn't pick them up
    _saved = {}
    for _var in (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "https_proxy",
        "http_proxy",
        "PLIVO_PROXY",
    ):
        _val = os.environ.pop(_var, None)
        if _val is not None:
            _saved[_var] = _val

    try:
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

        s3_kwargs = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            s3_kwargs["aws_access_key_id"] = aws_access_key_id
            s3_kwargs["aws_secret_access_key"] = aws_secret_access_key

        s3 = boto3.client("s3", **s3_kwargs)
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_bytes,
            ContentType="audio/mpeg",
            ACL="public-read",
        )
        url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
        logger.info(f"Uploaded recording to S3: {url}")
        return url
    except Exception as e:
        logger.error(f"S3 upload failed: {e}", exc_info=True)
        return None
    finally:
        os.environ.update(_saved)
