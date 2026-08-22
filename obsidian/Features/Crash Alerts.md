# Crash Alerts

**File:** `mantra/email_alerts.py` (244 lines)

## Overview

Automatic SMTP email alerts when the agent or UI server crashes. Uses formatted HTML with stack traces and optional meme images for admin recipients.

## Flow

1. Exception caught in global handler or agent entrypoint
2. `send_crash_email(service_name, error, context_data)` called
3. Runs via `asyncio.to_thread()` — non-blocking, doesn't freeze the event loop
4. Sends premium HTML email to `ALERT_EMAIL_IDS` + `ADMIN_MAIL_ID`
5. Admin recipients get randomized memes from `memegen.link` (tries 13 templates)

## Configuration

All SMTP env vars (see [[Knowledge/Environment.md]]):

- `SMTP_HOST`, `SMTP_PORT` (587 for TLS, 465 for SSL)
- `SMTP_USER`, `SMTP_PASSWORD` (Gmail app password)
- `SMTP_FROM_EMAIL` (defaults to `SMTP_USER`)
- `ALERT_EMAIL_IDS` — Comma-separated recipients (with memes)
- `ADMIN_MAIL_ID` — Comma-separated admin recipients (with memes)

## Meme Feature

Admin recipients get a randomized crash meme image embedded inline. Templates include: fine, pigeon, harold, disastergirl, rollsafe, sad-biden, spiderman, spongebob, buzz, doge, drake, trade, wonka, fry, panik-kalm-panik. Top text: `{service_name} crashed`, bottom text: `Error: {exception_type}`. Falls back gracefully if memegen.link is unreachable.
