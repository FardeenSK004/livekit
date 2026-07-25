# Restructure Verification Report

> **Date:** 2026-07-25  
> **Branch:** `feature/restructure`  
> **Verdict:** **GO WITH CAVEATS**  
> **Repo root copy:** [`report.md`](../../report.md) (same content; convenient for PR / review)

This vault page is the durable Obsidian copy of the final restructure parity verification. Prefer linking here from other vault notes; use `report.md` at the repo root when sharing outside Obsidian.

---

## 1. Executive verdict

The `app/` cutover works for local verification: imports, unit tests, UI/agent/dispatcher, LiveKit registration, SIP list, KB ingest/search, and authenticated dashboard APIs all behave. Two restructure bugs were found and fixed during verification. Remaining blockers are mostly **env/docs** and **known pre-existing prod issues**, not a broken package layout.

| Decision | Recommendation |
|----------|----------------|
| **Commit / push branch** | **Yes** — safe for review; include the two auth/JSON fixes |
| **Merge / deploy prod** | **Not yet** — complete env, fix MCP, then staged call smoke |

Related: [[Development/Restructure Implementation.md|Implementation]] · [[Architecture/Restructure Plan.md|Plan]] · [[Development/Current Sprint.md|Current Sprint]]

---

## 2. Environment

| Resource | Status |
|----------|--------|
| Branch | `feature/restructure` |
| `.env.local` | Present (~21 keys): LiveKit, STT/TTS/LLM keys, S3, MantraAssist webhook URL/secret |
| Missing from `.env.local` | `POSTGRES_*`, `JWT_SECRET`, `ADMIN_*_HASH`, `SIP_TRUNK_ID`; `REDIS_URL` optional (default OK) |
| Env mapping gaps | `GOOGLE_API_KEY` ≠ `GEMINI_API_KEY`; `CARTESIA_API_KEY_2/3` not folded into `CARTESIA_API_KEYS` |
| Redis `:6379` | Up (`PONG`) |
| Postgres `:5432` | `pgvector_db` up; **no `livekit` DB initially** — created + `migrations/*.sql` applied for verify |
| Port `:8081` | Occupied by **phpMyAdmin** (not this app) |
| Verify UI port | **8091** |
| LiveKit | Cloud URL from settings; agent **registered worker** |
| `mantra/` | Deleted; no runtime `from mantra` / `import mantra` in `app/` (comments only) |

---

## 3. What was started / what failed

| Process | Result |
|---------|--------|
| UI (`uvicorn app.main:app` on 8091) | Started; `/health` → `{"status":"ok","service":"ui_server"}` **200** |
| Dispatcher (`python -m app.routines`) | Started: `Dispatcher loop started` |
| Agent (`python -m app.agent.entrypoint dev`) | Started; `registered worker` |
| MCP via agent job | **Fails (caught):** `no attribute 'CstdioServerParameters'` — known blocker; agent continues with 3 tools |
| `./dev.sh` as written | Would collide with phpMyAdmin on **8081** unless `PORT` overridden |
| Real outbound SIP dial | Not attempted (no `SIP_TRUNK_ID` in env; no customer numbers) |

Verification DB: temporary `livekit` database + SQL migrations under `migrations/`.

---

## 4. Unit / import results

| Check | Result |
|-------|--------|
| pytest | **7 passed** (~2s) |
| Import smoke | `app.main`, agent entrypoint, routines/dispatcher, KB, services — all OK |
| Routes | **55** OpenAPI entries |
| Agent tools | **3** — `end_call`, `search_knowledge_base`, `transfer_to_human` |
| HMAC unit test | `{body}.{timestamp}` signing order matches pre-restructure — **pass** |
| Static paths | `app/main.py` + pages use repo-root `static/` (exists; `app/static/` copy also present) |

---

## 5. Endpoint test matrix

Base URL: `http://127.0.0.1:8091`  
Auth for re-verify: temporary JWT / admin hashes in process env (not committed to `.env.local`).  
**Final smoke: 39/39 PASS** (after the two fixes in §6).

| Endpoint | Method | Expected | Actual | Pass | Notes |
|----------|--------|----------|--------|------|-------|
| `/health` | GET | 200 | 200 | ✅ | `service=ui_server` |
| `/openapi.json` | GET | 200 | 200 | ✅ | |
| `/` (login page) | GET | 200 | 200 | ✅ | |
| `/dashboard` | GET | 200 | 200 | ✅ | |
| `/console` | GET | 200 | 200 | ✅ | |
| `/kb-chat` | GET | 200 | 200 | ✅ | |
| `/network` | GET | 200 | 200 | ✅ | |
| `/config` | GET | 200 | 200 | ✅ | LiveKit cloud URL |
| `/metrics` | GET | 200 | 200 | ✅ | Prometheus |
| `/static/favicon.png` | GET | 200 | 200 | ✅ | |
| `/static/app.js` | GET | 200 | 200 | ✅ | |
| `/static/dashboard.js` | GET | 200 | 200 | ✅ | |
| `/health` | OPTIONS | 405 OK | 405 | ✅ | No CORS middleware |
| `/api/v1/auth/login` (bad creds) | POST | 401 | 401 | ✅ | After auth env set |
| `/api/v1/auth/login` (good) | POST | 200 | 200 | ✅ | |
| `/api/v1/dashboard/*` (no token) | GET | 401 | 401 | ✅ | **Fixed** during verify |
| `/api/v1/dashboard/metrics` (auth) | GET | 200 | 200 | ✅ | |
| `/api/v1/dashboard/calls` (auth) | GET | 200 | 200 | ✅ | |
| `/api/v1/dashboard/active-calls` (auth) | GET | 200 | 200 | ✅ | |
| `/api/v1/dashboard/stream` (auth) | GET | 200 | 200 | ✅ | SSE |
| `/api/v1/org-configs` | GET | 200 | 200 | ✅ | Still unauthenticated |
| `/api/v1/org-configs/+1999…` | GET | 404 | 404 | ✅ | Missing config |
| `/api/v1/sip/trunks/outbound` | GET | 200 | 200 | ✅ | 68 trunks from LiveKit |
| `/api/v1/sip/trunks/inbound` | GET | 200 | 200 | ✅ | 4 trunks |
| `/api/v1/sip/dispatch-rules` | GET | 200 | 200 | ✅ | 5 rules |
| `/api/v1/sip/trunks/outbound/twilio` (empty) | POST | 400 | 400 | ✅ | Validation only |
| `/api/v1/sip/plivo-xml` | GET | 200 | 200 | ✅ | Hangup XML |
| `/api/v1/sip/twilio-webhook` | GET | 200 | 200 | ✅ | Reject XML |
| `/api/v1/webhooks/telephony` (empty) | POST | 400 | 400 | ✅ | |
| `/api/v1/webhooks/telephony` (bad JSON) | POST | 400 | 400 | ✅ | **Fixed** during verify |
| `/api/v1/webhooks/telephony` (partial) | POST | 500 | 500 | ✅ | `No SIP trunk ID configured` (env) |
| `/api/v1/test/inbound-call` (empty) | POST | 400 | 400 | ✅ | |
| `/dispatch-test` | POST | 200 | 200 | ✅ | Room + token; agent joined |
| `/api/v1/kb/search` | POST | 200 | 200 | ✅ | |
| `/api/v1/knowledge/list` | GET | 200 | 200 | ✅ | |
| `/api/v1/knowledge/text` (ingest) | POST | 200 | 200 | ✅ | |
| `/api/v1/kb/search` (after ingest) | POST | 200 | 200 | ✅ | Hit returned |

**HMAC note:** Inbound telephony HMAC (bad sig → 401) was **N/A** for this webhook — it is an outbound dispatch trigger. HMAC applies to **outbound** delivery to MantraAssist (covered by unit test).

---

## 6. Fixes made during verification

### 6.1 Dashboard JWT not wired

- **File:** `app/routers/dashboard.py`
- **Issue:** `require_auth` existed but was unused; `/api/v1/dashboard/*` returned **200** without a token
- **Fix:** Router-level `dependencies=[Depends(require_auth)]` on all dashboard routes
- **Result:** Unauthenticated → **401**; authenticated → **200**

### 6.2 Malformed telephony JSON → 500

- **File:** `app/routers/webhooks.py`
- **Issue:** Unhandled `JSONDecodeError` on invalid body
- **Fix:** Catch parse errors → **400** with `"Invalid JSON payload"`
- **Result:** Bad JSON → **400** instead of unhandled **500**

---

## 7. Agent / dispatcher results

- Dispatcher: healthy loop; capacity limits logged
- Agent: registered with LiveKit; `agent_name=mantra-agent`
- MCP: fails per job with known `CstdioServerParameters` error; fallback to 3 tools
- `/dispatch-test` created a job; agent hit **OpenAI 401** (`Incorrect API key`) during that session — **env/key issue**, not import/crash
- No real phone E2E

---

## 8. Regressions vs pre-existing

### Fixed during this verification (restructure gaps)

1. Dashboard JWT not wired (see §6.1)
2. Malformed telephony JSON → 500 (see §6.2)

### Confirmed working (parity)

- Entrypoints: `pyproject.toml` / `dev.sh` / `entrypoint.sh` / `Dockerfile` → `app.*`
- 55 routes, static under `/static`, pages OK
- Webhook HMAC sign order `{body}.{timestamp}`
- 3 agent tools + MCP try/except
- SIP list against LiveKit cloud
- KB ingest/search on migrated schema

### Pre-existing / env (not restructure regressions)

| Issue | Notes |
|-------|-------|
| MCP `CstdioServerParameters` | Upstream LiveKit agents API change |
| Empty KB for org 66 | Prod data gap |
| n8n webhook 404 | External ngrok/backend route missing |
| Handoff TTS `"..."` glitch | Race after `transfer_to_human` |
| OpenAI 401 on dispatch-test | Bad/missing API key in env |
| Incomplete `.env.local` | Postgres / JWT / SIP missing |
| `GOOGLE_API_KEY` / Cartesia multi-key mapping | Settings field names differ |
| README documenting `mantra/` | Docs lag — updated after this report |
| Host **8081** taken by phpMyAdmin | Use `PORT=8091` locally |

---

## 9. Gaps not tested

- Real inbound/outbound SIP to a test number
- Full post-call finalize → n8n + S3 recording E2E
- Gemini / multi-Cartesia fallback keys
- MCP tools after upstream API fix
- Org-config / KB write auth hardening (still open if old monolith protected them)
- Docker image build/run
- Default `./dev.sh` on 8081 without `PORT` override

---

## 10. Recommendation

| Action | Recommendation |
|--------|----------------|
| **Commit/push branch** | **Yes** — restructure is verifiable; include the two auth/JSON fixes |
| **Merge/deploy prod** | **After** filling Postgres/JWT/SIP in deploy env, resolving MCP, and a staged call test |
| **Before next local `./dev.sh`** | Set `PORT=8091` (or free 8081); add `POSTGRES_*` + JWT hashes to `.env.local`; ensure `livekit` DB exists |

**Code changed in this verification:**

- `app/routers/dashboard.py` — JWT on all dashboard routes
- `app/routers/webhooks.py` — invalid JSON → 400

Smoke artifacts (not in repo): `/tmp/restructure-verify/smoke_endpoints.py`, `smoke_results.json`.
