# Changelog

All notable changes to this project are documented in this file.

## [1.0.0] - 2026-08-29

### Added
- Standardized project structure mirroring `support-bot`:
  - `app.py`: FastAPI server setup with lifespan, CORS, metrics, and modular routers.
  - `routers/`: Modular route handlers (`auth`, `health`, `telephony`, `sip`, `kb`, `org_configs`, `dashboard`, `redis`).
  - `controllers/`: Dedicated controllers separating HTTP handling from business logic.
  - `core/`: Core agents, dispatcher loop, language manager, AMD detection, tools, and KB engines.
  - `services/`: Telephony provider management, LiveKit API clients, SessionRecorder, and S3 service.
  - `dependencies/`: FastAPI dependencies for DB pools, Redis, LiveKit, and JWT authentication.
  - `models/`: Pydantic and database schemas (`call_log`, `call_event`, `kb`, `org_config`).
  - `helpers/`: Utilities for alerts, DB logging, phone formatting, telemetry, and HMAC webhooks.
  - `routines/`: Background routines (`dispatcher`, `webhook_worker`, `process_reconcile`).
  - `scripts/`: Operational CLI scripts (`backfill_embeddings`, `migrate`, `seed_kb`).
  - `validators/`: Request and data validation modules.
  - `constants/`: Centralized events, languages, timeouts, and voice mappings.
  - `configs/`: Centralized agent runtime and voice configuration.
  - `custom_types/`: Pydantic models and type definitions.
  - `migrations/`: Consolidated PostgreSQL schema migrations.
- Added `docker-compose.yaml`, `ruff.toml`, `mypy.ini`, and `Environment.md`.
- Backward-compatible shims in `mantra/` package for zero-downtime transition.
