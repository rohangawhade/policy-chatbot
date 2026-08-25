# PolicyPal

A RAG-powered chatbot that answers employees' and employers' benefits policy questions, scoped to their own company's enrolled plans.

## What This Project Does

PolicyPal lets an employee log in and ask plain-English questions like "What's my dental deductible?" or "Am I covered for physical therapy?" and get an answer sourced from their own employer's actual policy documents — not a generic chatbot guess. It refuses to answer anything outside benefits/policy topics, and every answer cites which document and section it came from. Employers upload their plan documents once; admins get a dashboard showing what people are asking, what it's costing, and where the bot is struggling.

## Architecture Overview

The backend is a FastAPI service built with hexagonal (ports & adapters) architecture: business logic in `core/` never imports a framework or a specific database/vector-store/LLM library directly — it depends only on abstract interfaces (`core/ports/`), and concrete implementations (`adapters/`) plug into those interfaces at the API layer. This means swapping Pinecone for another vector DB, or adding a new LLM provider, is a new adapter file, not a rewrite.

```
User Query → Guardrails (off-topic reject) → Redis cache check → Query Router
  (cheap vs powerful model) → Embed query → Pinecone search (tenant-scoped)
  → assemble prompt with retrieved chunks + enrollment data → stream LLM
  response over SSE → cache + persist → analytics events (cost, latency,
  low-confidence flags) logged for the admin dashboard
```

Document ingestion runs the same way in reverse: uploaded PDF/DOCX/XLSX/XML → the right processor (via a factory, keyed on file type) → metadata extraction → semantic chunking → embeddings → Pinecone (namespaced per employer) + Postgres chunk references, all as a Celery background task.

See `files/plan.md` for the full design (tech stack rationale, data flow diagrams, phase-by-phase implementation plan) and `files/coding-standards.md` for the engineering rules this codebase follows.

## Features

- [x] Git delivery workflow: trunk-based, protected `main`, Conventional Commits, CI gates (Phase 0)
- [x] Project scaffolding: backend/frontend skeletons, tooling (Phase 1)
- [x] Docker Compose: postgres, redis, backend, celery-worker, frontend — with hot reload for local dev
- [x] PostgreSQL schema + Alembic migrations
- [x] Typed configuration (Pydantic Settings)
- [x] Health/readiness probes
- [x] Core domain models, ports & events (Phase 2)
- [x] Infrastructure adapters: LiteLLM, Pinecone, Redis, Postgres repos, document processors (Phase 3)
- [x] Chunking & embedding pipeline: metadata extraction, semantic chunking, embedding + Pinecone indexing (Phase 4)
- [x] Auth + multi-tenancy: JWT access/refresh tokens, role guards, tenant context middleware (Phase 5)
- [x] RAG pipeline: guardrails, query routing, retrieval, prompt assembly, streaming generation, conversation memory (Phase 6)
- [x] Document versioning: version tracking, vector/chunk replacement, cache invalidation (Phase 7)
- [x] Celery ingestion workers: queue routing, retries, dead-letter handling, full ingestion pipeline, status tracking (Phase 8)
- [ ] API routes (Phase 9)
- [ ] React chat UI + admin dashboard (Phase 10)
- [ ] Data acquisition & seeding (Phase 11)
- [ ] RAGAS evaluation pipeline (Phase 12)
- [ ] DI audit (Phase 13)
- [ ] Production polish: logging, error handling, rate limiting (Phase 14)

Track detailed step-by-step progress in `IMPLEMENTATION_STATUS.md`.

## Tech Stack

| Layer               | Technology                                   |
| -------------------- | --------------------------------------------- |
| Backend API          | FastAPI (async, Python 3.11+)                 |
| LLM Gateway          | LiteLLM                                       |
| RAG Pipeline         | Custom-built                                  |
| Vector Database      | Pinecone                                      |
| Relational Database  | PostgreSQL (SQLAlchemy async + Alembic)       |
| Authentication       | OAuth2 + JWT                                  |
| Background Jobs      | Celery + Redis                                |
| Caching              | Redis                                         |
| Document Parsing     | PyMuPDF (PDF), python-docx, openpyxl, lxml    |
| Frontend             | React 18 + TypeScript + Tailwind CSS + Vite   |
| Streaming            | Server-Sent Events (SSE)                      |
| Containerization     | Docker Compose                                |
| RAG Evaluation       | RAGAS + golden dataset + user feedback        |
| CI/CD                | GitHub Actions                                |

<details>
<summary>🛠️ Prerequisites</summary>

- Python 3.11+ (developed against 3.12)
- Node.js 20+ (developed against 22)
- Docker + Docker Compose
- A GitHub account with `gh` CLI if you're contributing (see `CONTRIBUTING.md`)

</details>

<details>
<summary>📦 Environment Setup</summary>

```bash
git clone https://github.com/rohangawhade/policy-chatbot.git
cd policy-chatbot
cp .env.example .env   # fill in real values — see "API Keys & Model Configuration" below
make install            # creates backend/.venv and installs both backend + frontend deps
```

</details>

<details>
<summary>🐳 Running with Docker</summary>

```bash
cp .env.example .env   # fill in real values
docker compose up
```

This brings up five services: `postgres`, `redis`, `backend` (FastAPI, hot-reload via `--reload`), `celery-worker`, and `frontend` (Vite dev server). `docker-compose.override.yml` is applied automatically and gives you hot reload for both backend and frontend — it's not something you need to reference explicitly.

- Backend: http://localhost:8000
- Frontend dev server: http://localhost:5173
- Postgres: `localhost:5432` (user/password/db: `policypal`)
- Redis: `localhost:6379`

Inside the Compose network, services reach each other by service name (`redis`, `postgres`), not `localhost` — `docker-compose.yml` overrides `DATABASE_URL`/`REDIS_URL`/`CELERY_*` accordingly; you don't need to edit `.env` for this.

`docker compose down -v` stops everything and removes the Postgres volume (fresh database next time).

**Adding a new Celery task family**: `workers/celery_app.py`'s `task_routes` sends each task-name prefix (e.g. `embedding.*`) to its own queue. A new prefix needs two changes, not one — the `task_routes` entry *and* `-Q` on the `celery-worker` command in both `docker-compose.yml` and `docker-compose.override.yml` — a queue nothing consumes just accumulates unprocessed tasks silently, with no error. `dead_letter` is deliberately never in `-Q`: it's where a task lands after exhausting its own retries, for manual inspection/replay via a one-off `celery -A workers.celery_app worker -Q dead_letter`, not automatic reprocessing.

</details>

<details>
<summary>🗄️ Database Setup</summary>

```bash
docker compose up -d postgres   # or `make up` for the full stack
make migrate                     # applies alembic upgrade head
```

Verify tables exist:

```bash
docker compose exec postgres psql -U policypal -d policypal -c "\dt"
```

Thirteen tables: `employers`, `employees`, `policies`, `employee_policies` (enrollment), `documents`, `document_chunks`, `conversations`, `messages`, `feedback`, `llm_cost_logs`, `request_latency_logs`, `flagged_responses`, `guardrail_rejections`.

Tenant isolation is baked into the schema, not just query-time discipline: every tenant-scoped table carries an indexed `employer_id` (denormalized onto `messages`, `feedback`, `document_chunks`, and `flagged_responses` too, so those tables don't need a join through their parent to be scoped by employer).

To generate a new migration after changing `backend/src/adapters/persistence/models.py`:

```bash
cd backend
.venv/Scripts/alembic.exe revision --autogenerate -m "describe the change"
```

**If your change adds a new Postgres ENUM column** (or a new value to `models.py`'s `PyEnum` classes), check the generated migration — Alembic auto-creates the enum type on `create_table`/`add_column`, but does **not** auto-drop it in `downgrade()`. Follow the pattern already in `alembic/versions/*_initial_schema.py`: define the type once at module level with `create_type=False`, `.create(bind, checkfirst=True)` at the top of `upgrade()`, `.drop(bind, checkfirst=True)` at the end of `downgrade()`. Skipping this makes `downgrade` → `upgrade` fail with `type "..." already exists` — this bit us during Step 1.3, and `migration-check.yml` now runs a downgrade-then-upgrade cycle specifically to catch it before merge.

</details>

<details>
<summary>📄 Loading Documents</summary>

Not yet available — the document download/generation/seed scripts land in Phase 11.

</details>

<details>
<summary>🔑 API Keys & Model Configuration</summary>

See `.env.example` for the full list of environment variables. Model tiers are entirely config-driven (`LLM_CHEAP_MODEL`, `LLM_POWERFUL_MODEL`, `LLM_EMBEDDING_MODEL`) — if `LLM_POWERFUL_MODEL` is left empty or its provider key is missing, every query automatically falls back to the cheap model tier. No code changes needed.

All configuration is typed and validated via `backend/src/config.py` (Pydantic Settings) — one class per concern (`AppConfig`, `DatabaseConfig`, `RedisConfig`, `CacheConfig`, `CeleryConfig`, `PineconeConfig`, `LLMConfig`, `AuthConfig`, `CorsConfig`), each reading only its own env-var prefix. For local host-based development it also reads the repo-root `.env` automatically (no manual `source .env` needed) — real environment variables (e.g. Docker Compose's overrides) always win over the file.

</details>

<details>
<summary>🧪 Running RAG Evaluation</summary>

Not yet available — lands in Phase 12.

</details>

<details>
<summary>🔧 Common Issues & Troubleshooting</summary>

Nothing tracked yet — this section grows as issues are discovered and fixed.

</details>

## API Endpoints

| Method | Path                                     | Auth               | Description                                                                                     |
| ------ | ----------------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------- |
| GET    | `/health`                                 | None                | Liveness probe — 200 if the process is up. No dependency checks.                                  |
| GET    | `/ready`                                  | None                | Readiness probe — checks PostgreSQL and Redis (required) and Pinecone (if configured). 503 if not ready. |
| POST   | `/api/auth/register`                      | None                | Create an `employer`- or `employee`-role account under an existing employer; returns a token pair. |
| POST   | `/api/auth/login`                         | None                | OAuth2 password flow (email as `username`); returns an access + refresh token pair.               |
| POST   | `/api/auth/refresh`                       | Refresh token        | Exchange a refresh token for a new access token.                                                  |
| GET    | `/api/auth/me`                            | Access token         | The authenticated account's own profile.                                                          |
| GET    | `/api/documents/{id}/status`              | Access token (employer-scoped) | A document's current ingestion status (`processing`/`ready`/`failed`).                 |
| GET    | `/api/documents/{id}/status/stream`       | Access token (employer-scoped) | SSE stream of ingestion status until it reaches a terminal state.                       |

Remaining Phase 9 routes (chat, document upload/list/delete, employer/employee management, feedback, admin analytics) land next. This table will be kept current as endpoints are added.

## Project Structure

```
policypal/
├── docker-compose.yml            # postgres, redis, backend, celery-worker, frontend
├── docker-compose.override.yml   # local dev: hot reload, source mounts
├── backend/
│   ├── src/
│   │   ├── main.py              # FastAPI app factory
│   │   ├── core/                # Domain models, ports, services — zero framework imports
│   │   ├── adapters/            # LiteLLM, Pinecone, Redis, Postgres, document processors
│   │   ├── api/                 # Routes, middleware, DI wiring
│   │   └── workers/             # Celery tasks
│   └── scripts/                 # Seed data, doc download/generation
├── frontend/
│   └── src/                     # React 18 + TypeScript + Tailwind (Vite)
├── data/eval/                   # Golden Q&A dataset for RAG evaluation
├── eval/                        # RAGAS evaluation runner
└── files/                       # Project plan and coding standards (source of truth)
```

Full target structure is in `files/plan.md` under "Folder Structure."

## How It Works (Layman's Terms)

An employer uploads their benefits documents once. Behind the scenes, PolicyPal reads those documents, breaks them into meaningful chunks, and stores them so it can find the relevant part instantly later — like a very good index at the back of a book, except it understands meaning, not just keywords.

When an employee asks a question, PolicyPal first checks the question is actually about benefits (it politely declines anything else), looks up the most relevant chunks from that employer's documents, checks the employee's own enrollment records if the question is personal ("what am I covered for"), and then asks an AI model to write an answer using only that retrieved information — citing exactly which document it came from. Simple questions go to a cheap, fast model; more complex ones (comparisons, multi-policy questions) automatically route to a more capable model. Everything is logged so an admin can see what's costing money, what's slow, and what the bot is struggling to answer well.
