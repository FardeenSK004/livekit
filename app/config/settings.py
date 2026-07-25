"""Application settings — single source of truth for all env vars.

Usage:
    from app.config import settings
    settings.LIVEKIT_URL  # str, validated at import time
"""

from __future__ import annotations

import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── LiveKit ────────────────────────────────────────────────────────
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_SIP_DOMAIN: str = ""
    SIP_DOMAIN: str = ""

    # Plivo uses HTTP proxy for LiveKit API calls (India routing)
    PLIVO_PROXY: str = ""
    # Aliases kept for forward-compat with restructure docs
    PLIVO_PROXY_URL: str = ""
    PLIVO_PROXY_API_KEY: str = ""
    PLIVO_PROXY_API_SECRET: str = ""

    # ── SIP Trunks ─────────────────────────────────────────────────────
    SIP_TRUNK_ID: str = ""
    SIP_TRUNK_ID_ZADARMA: str = ""
    SIP_TRUNK_ID_TWILIO: str = ""
    TRANSFER_SIP_TRUNK_ID: str = ""
    TRANSFER_DEFAULT_NUMBER: str = ""
    TRANSFER_NUMBERS: str = ""  # JSON object, e.g. {"refund": "+91..."}

    # ── Telephony provider credentials ─────────────────────────────────
    ZADARMA_API_KEY: str = ""
    ZADARMA_KEY: str = ""
    ZADARMA_API_SECRET: str = ""
    ZADARMA_SECRET: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    PLIVO_AUTH_ID: str = ""
    PLIVO_AUTH_TOKEN: str = ""

    # ── Redis ──────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── PostgreSQL ─────────────────────────────────────────────────────
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "livekit"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"

    # ── JWT Auth ───────────────────────────────────────────────────────
    JWT_SECRET: str = ""
    ADMIN_USERNAME_HASH: str = ""
    ADMIN_PASSWORD_HASH: str = ""

    # ── Cartesia TTS ───────────────────────────────────────────────────
    CARTESIA_API_KEY: str = ""
    CARTESIA_API_KEYS: str = ""  # comma-separated, for FallbackAdapter
    CARTESIA_MAX_CONCURRENCY: int = 5

    # ── Deepgram STT ───────────────────────────────────────────────────
    DEEPGRAM_API_KEY: str = ""

    # ── OpenAI / LLM ───────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # ── AWS S3 ─────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET_NAME: str = ""
    AWS_BUCKET_NAME: str = ""  # legacy alias

    # ── MantraAssist Backend ───────────────────────────────────────────
    MANTRAASSIST_BACKEND_URL: str = ""
    MANTRAASSIST_WEBHOOK_SECRET: str = ""

    # ── SMTP Alerts ────────────────────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: str = "587"
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    ALERT_EMAIL_IDS: str = ""
    ADMIN_MAIL_ID: str = ""

    # ── Capacity ───────────────────────────────────────────────────────
    MAX_CONCURRENCY: int = 5
    LIVEKIT_MAX_ROOMS: int = 20
    AGENT_MAX_WORKERS: int = 20

    # ── Agent Behavior ─────────────────────────────────────────────────
    CALL_DURATION_LIMIT_SECONDS: int = 180
    INACTIVITY_TIMEOUT_SECONDS: int = 10
    LOCAL_INBOUND_MAPPINGS: bool = False

    # ── Server ─────────────────────────────────────────────────────────
    PORT: int = 8081

    # ── Feature Flags / OTEL ───────────────────────────────────────────
    LIVEKIT_AGENTS_INFERENCE: bool = False
    OTEL_METRICS_EXPORTER: str = "none"
    OTEL_LOGS_EXPORTER: str = "none"
    OTEL_TRACES_EXPORTER: str = "none"

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def plivo_proxy(self) -> str:
        """Effective Plivo proxy URL (prefers PLIVO_PROXY)."""
        return self.PLIVO_PROXY or self.PLIVO_PROXY_URL

    @property
    def s3_bucket(self) -> str:
        return self.AWS_S3_BUCKET_NAME or self.AWS_BUCKET_NAME

    @property
    def effective_max_concurrency(self) -> int:
        """MAX_CONCURRENCY with CARTESIA_MAX_CONCURRENCY fallback (legacy)."""
        # If MAX_CONCURRENCY was left at default but CARTESIA override is set via env,
        # pydantic already bound MAX_CONCURRENCY from env when present.
        return self.MAX_CONCURRENCY

    @property
    def transfer_numbers_map(self) -> dict[str, str]:
        raw = (self.TRANSFER_NUMBERS or "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            pass
        return {}

    @property
    def cartesia_api_keys_list(self) -> list[str]:
        return [k.strip() for k in self.CARTESIA_API_KEYS.split(",") if k.strip()]

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()

# ── Derived / computed values ─────────────────────────────────────────
CARTESIA_API_KEYS_LIST = settings.cartesia_api_keys_list
