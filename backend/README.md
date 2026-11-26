# THE PANTHEON — Backend (COMPANY_OS_PY_BE)

FastAPI backend and LangGraph deliberation workflow for the divine council MVP.
Four independent executive assessments (CEO, CFO, CTO, CSO), deterministic
position extraction, claim-targeted cross-examination, explicit position
revisions, a consolidated board-chair recommendation, and Founder-controlled
decree recording.

## Included
- FastAPI application (`app/main:app`)
- SQLAlchemy models (local Postgres by default; persistent Postgres in production)
- LangGraph board deliberation graph (assess → extract → cross-examine → revise → synthesize)
- Local inference through LM Studio or Ollama, plus configurable hosted AI providers
- REST API under `/api` (health, executives, board meetings)

## Requirements
- Python 3.11+
- LM Studio, Ollama, or an API key from a supported hosted provider
- PostgreSQL 15+ (the included Docker Compose database is the local default)

## Quick start

```bash
# Start the local Postgres used by default (localhost:5433)
docker compose up -d db

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create the environment file from the example
cp .env.example .env
# DATABASE_URL already points at the local Postgres above. Point it at your own
# system Postgres if you prefer. Edit .env to route roles to a cloud provider
# (set CLOUD_API_KEY) and set CLERK_ISSUER for the Clerk instance used by the UI.

# Start the API from the repository root using the project interpreter
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# Windows: .venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

## Environment variables
Copy `.env.example` to `.env` and adjust as needed. When running from `backend/`,
settings are read from `backend/.env`; real process environment variables win.
The Neon CLI's repo-root `.env.local` is deliberately not loaded by the app, so
local runs always use local Postgres. Deployed Vercel injects `DATABASE_URL` from
its dashboard (see `app/config.py`).

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection string (local default: the Docker Postgres at `localhost:5433`; Vercel sets the pooled Neon URL) |
| `DATABASE_URL_UNPOOLED` | Optional direct connection for migrations/admin jobs |
| `API_CORS_ORIGINS` | `*` to allow all browser origins, or a comma-separated frontend-origin allowlist |
| `CLERK_ISSUER` | HTTPS issuer URL for the Clerk instance; required for authenticated API routes |
| `LLM_CONFIG_ENCRYPTION_KEY` | Stable Fernet key used to encrypt provider API keys saved through Model Sources; required to manage sources in the UI |
| `LOCAL_BASE_URL` / `LOCAL_API_KEY` / `LOCAL_MODEL` | LM Studio endpoint |
| `CLOUD_BASE_URL` / `CLOUD_API_KEY` / `CLOUD_MODEL` | OpenAI-compatible cloud endpoint |
| `*_PROVIDER` | `local` or `cloud` per role (CEO, CFO, CTO, CSO, BOARD) |
| `*_MODEL` | Optional per-role model override |
| `AGENT_CONCURRENCY` | Parallel agent call limit (default: `1`) |
| `PROGRESS_INITIAL_AGENT_SECONDS` | Starting per-agent duration for the approximate ETA; recalibrated from completed calls in each run (default: `60`) |
| `BOARD_SYNTHESIS_MAX_INPUT_CHARS` | Maximum BOARD synthesis input size for every provider (default: `6000` characters); reduce for smaller context windows or provider TPM limits |

Generate `LLM_CONFIG_ENCRYPTION_KEY` once with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
Set it in the backend `.env` for local development and in the backend service's
environment settings for hosted deployments (for example, Render), then restart
or redeploy the backend. Keep the same value for every deployment that shares a
database; losing or rotating it makes saved API keys unreadable. Use a separate
key for an isolated database/environment. Existing environment-based model
settings are imported into the database on startup when this key is configured;
otherwise they remain as a runtime fallback until model sources are added.

The authenticated **Model Sources** page supports LM Studio and Ollama; hosted
OpenAI-compatible APIs from OpenAI, OpenRouter, Groq, Together AI, Fireworks AI,
Mistral AI, DeepSeek, xAI, Cerebras, and compatible custom endpoints; and native
Anthropic Claude and Google Gemini APIs. It can test connectivity and discover
models using each provider's API, then route each executive independently.
Custom providers must expose the OpenAI-compatible `/models` and
`/chat/completions` endpoints. Local inference servers must be reachable from
the backend host; `localhost` refers to the API machine, not the browser. For
hosted backends, use an address reachable by the deployed backend rather than
the developer machine's `localhost`.

## Databases by environment

The included `docker-compose.yml` runs the local PostgreSQL 16 database:

```bash
docker compose up -d db
```

`DATABASE_URL` in `.env.example` already points at it
(`postgresql+psycopg://companyos:change-me-before-use@localhost:5433/companyos`).
Change that value to use your own system Postgres instead.

For the deployed Vercel backend, set `DATABASE_URL` in the Vercel project's
environment variables to the **pooled** Neon connection string and redeploy.
Serverless filesystems are ephemeral, so SQLite or `/tmp` is never suitable for
the hosted instance. Neon's `.env.local` is tooling output only — the app does
not read it, which keeps fresh clones on their own Postgres.

## API endpoints
- `GET /api/health`
- `GET /api/executives` (authenticated)
- `GET /api/meetings` (authenticated)
- `POST /api/meetings` (authenticated)
- `GET /api/meetings/{id}` (authenticated)
- `POST /api/meetings/{id}/run` (authenticated; returns `202 Accepted` while deliberation continues in the background)
- `GET /api/meetings/{id}/progress?after_id=0` (authenticated; meeting status, incremental run events, progress percentage, elapsed time and approximate ETA)
- `POST /api/meetings/{id}/decision` (authenticated)

The frontend sends the Clerk session JWT as a bearer token. Set `CLERK_ISSUER` to
the exact HTTPS issuer shown in the Clerk instance's JWT. `API_CORS_ORIGINS=*`
allows all browser origins and Clerk `azp` values; otherwise configure the exact
frontend origins (including scheme and port).
The API verifies the token's
signature using the Clerk instance's JWKS, validates issuer and expiry, and checks
that its `azp` claim matches an origin in `API_CORS_ORIGINS` when an allowlist is
configured. With `*`, the API still requires a valid Clerk bearer token, but any
browser origin may call it. `/api/health` remains public for deployment health checks.

Each board run stores phase and agent start/completion/failure events in
`meeting_run_events`. Generated response text is streamed into bounded chunks
and persisted as `agent_output` events; it is the agents' visible response, not
private chain-of-thought. The progress endpoint returns up to 100 events after
the provided event ID, allowing clients to poll without reloading the full run
log. Its ETA starts from `PROGRESS_INITIAL_AGENT_SECONDS` and recalibrates from
completed agent response times during the current run. It is an estimate, not a
deadline, and can vary with local model load and output length. Failed meetings
can be retried; each attempt remains available in the event history.

Completed agent responses are also saved as per-meeting checkpoints in
`meeting_run_checkpoints`. A retry restores those outputs and runs only agents
without a completed checkpoint. Existing streamed event logs are backfilled into
checkpoints on retry, so completed work from runs created before checkpoint
storage was added can also be reused. On API startup, any run left in `running`
is marked interrupted and retryable; the next retry continues from its saved
checkpoints. Run the API as a single worker because background tasks are
process-local. An agent whose inference was interrupted mid-response must be
rerun because OpenAI-compatible inference APIs do not expose resumable token
generation state. The database preserves its partial streamed output. Run writes
are fenced by the active attempt: a stale worker cannot append progress,
replace a checkpoint, or overwrite the result of a newer retry.

BOARD synthesis uses a bounded prompt for every provider that retains excerpts
from the meeting context and every executive assessment, challenge, and position
revision. Full agent responses remain in the meeting checkpoints and history. If
a provider reports a context-length or total tokens-per-minute limit error,
synthesis retries with a smaller prompt without rerunning the executives. The
character limit is a conservative proxy, not an exact token count; lower
`BOARD_SYNTHESIS_MAX_INPUT_CHARS` for a smaller model context window or tighter
provider rate limits.

Versioned executive identity profiles are applied to every executive call. Each
profile defines expertise, responsibilities, decision boundaries, evidence
limits, evaluation criteria, expected challenges, and relationships to the other
executives. The deterministic position-extraction phase builds stable IDs for
each position, recommendation, and classified assessment claim; it adds no LLM
call. Each executive then cross-examines one cited claim from each peer, and
challenge outputs are validated against those IDs before checkpointing.

New executive assessments, targeted challenges, position revisions, and BOARD
syntheses must match validated Pydantic contracts. Every assessment claim is tagged as verified,
founder-provided, assumption, estimate, hypothesis, or unknown. Each executive
must state whether the position is maintained, revised, or withdrawn; unchanged
positions and unresolved dissent are valid outcomes. BOARD output separates
shared conclusions, disagreements, material dissent, evidence classifications,
unresolved questions, next actions, and decision gates. Malformed or incomplete
structured output fails that agent phase and is recorded as an error; it is not
silently accepted.

The public meeting response keeps its existing assessment and critique string
fields and adds an optional `revision` field to contributions. Position
extraction and revisions are stored in the existing `meeting_run_checkpoints`
table; no database migration is required. Existing structured v1 checkpoints
that predate `decision_gates` are upgraded only when restored, with an explicit
compatibility note and no inferred gates. New model responses must include the
field. Historical free-form assessments and challenge reports remain readable
and are labeled as legacy, unstructured input when used in a retry. Retry,
streaming, attempt fencing, and progress behavior remain in place; extraction
adds no inference call or ETA cost.

## Evidence Register and research

The authenticated Evidence Register stores claims with a scientific, technical,
financial, commercial, regulatory, or operational category; an evidence
classification; source title/reference/URL; publication and retrieval dates;
quality and limitations; executive reliance; and challenge/dispute status.
Claims marked `verified` require a source reference or URL and a verification
note. That note records the founder's attestation; it is not an independent
audit of the source.

Research search is available through authenticated `POST /api/research/search`.
Built-in providers search PubMed, ClinicalTrials.gov, and openFDA 510(k)
records. Optional general web search uses Tavily. Configure its API key from
the Evidence Register UI; it is encrypted with `LLM_CONFIG_ENCRYPTION_KEY`,
and the API returns only whether the key is configured. Without an encryption
key, public providers remain available but Tavily key storage is disabled.
Search results carry provider, source URL/reference, retrieval date, excerpt,
and limitations. They are discovery leads only: results never create
`verified` claims automatically, and snippets are not evidence of source
applicability.

The meeting form can attach up to 12 existing records before starting a run.
The backend copies their provenance into a meeting checkpoint at run start;
that snapshot is reused on retry and returned as `evidence_register` in meeting
progress. Assessment and challenge citations must reference IDs in that
snapshot. A cited `verified` claim is still a human-attested register claim,
not an automated source-content check. Deleting or later editing a register
entry does not rewrite a completed meeting's snapshot. Model prompts use a
6,000-character evidence-context ceiling, retain all attached record IDs, and
omit raw search excerpts; source metadata and limitations are compacted to help
keep local-model context bounded.

New `evidence_records`, `meeting_evidence_links`, and
`research_provider_configs` tables are created by the existing SQLAlchemy
`create_all` startup behavior; existing meeting and report fields remain
compatible. Startup also adds missing `source_provider`, `challenged_by`, and
`disputed_by` columns with safe defaults to older `evidence_records` tables,
preserving existing claims.
Research requests use fixed provider endpoints, a 15-second timeout, no
redirects, and at most 10 results per provider. PubMed and
ClinicalTrials.gov support literature/clinical-trial discovery; openFDA here
is limited to 510(k) records. Broad market discovery requires Tavily, and
external provider availability/rate limits may affect search results.

Decision actions: `approve`, `reject`, `revise`, `defer`.

## Governance
This is a decision-support prototype, not a legally constituted council. Agents have no
email, payment, shell, Git write, deployment or clinical-device permissions. Founder
decrees are explicit; silence is never approval.