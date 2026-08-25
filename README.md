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
- [x] API routes: auth, chat, documents, employers/employees/policies, feedback, admin analytics, health (Phase 9)
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

**Uploaded documents**: `backend` (the upload route) and `celery-worker` (the ingestion task) are separate containers, so uploaded files are saved to the `document_uploads` named volume — mounted at `/app/uploads` in both services — not either container's own ephemeral filesystem. `docker compose down -v` also removes this volume.

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
| POST   | `/api/chat/conversations`                 | Access token         | Create a new conversation for the current user.                                                   |
| GET    | `/api/chat/conversations`                 | Access token         | List the current user's own conversations.                                                        |
| GET    | `/api/chat/conversations/{id}/messages`   | Access token (owner-scoped) | Get a conversation's message history.                                                      |
| POST   | `/api/chat/conversations/{id}/messages`   | Access token (owner-scoped) | Send a message; returns an SSE stream of response tokens ending with a `done` event. |
| POST   | `/api/documents/upload`                   | Access token (employer or admin) | Upload a benefits document for ingestion. Returns the new `PROCESSING` document.      |
| GET    | `/api/documents`                          | Access token         | List documents for the current employer.                                                          |
| DELETE | `/api/documents/{id}`                     | Access token (employer or admin) | Remove a document and purge its vectors.                                                 |
| POST   | `/api/employers`                          | Admin only            | Create an employer (tenant).                                                                     |
| GET    | `/api/employers`                          | Admin only            | List all employers.                                                                              |
| GET    | `/api/employers/{id}`                     | Admin only            | Get one employer.                                                                                 |
| PATCH  | `/api/employers/{id}`                     | Admin only            | Update an employer (partial).                                                                     |
| DELETE | `/api/employers/{id}`                     | Admin only            | Delete an employer.                                                                               |
| POST   | `/api/employees`                          | Access token (employer or admin) | Create an employee/employer-contact account under an employer (no tokens returned).      |
| GET    | `/api/employees`                          | Access token (employer or admin) | List employees for the current employer.                                                 |
| GET    | `/api/employees/me/policies`              | Access token          | The current user's own enrolled policies.                                                        |
| GET    | `/api/employees/{id}`                     | Access token (employer or admin) | Get one employee.                                                                         |
| PATCH  | `/api/employees/{id}`                     | Access token (employer or admin) | Update an employee (partial).                                                            |
| DELETE | `/api/employees/{id}`                     | Access token (employer or admin) | Delete an employee.                                                                       |
| POST   | `/api/policies`                           | Access token (employer or admin) | Create a policy.                                                                          |
| GET    | `/api/policies`                           | Access token          | List policies for the current employer.                                                          |
| GET    | `/api/policies/{id}`                      | Access token          | Get one policy.                                                                                   |
| PATCH  | `/api/policies/{id}`                      | Access token (employer or admin) | Update a policy (partial).                                                               |
| DELETE | `/api/policies/{id}`                      | Access token (employer or admin) | Delete a policy.                                                                          |
| POST   | `/api/policies/{id}/enroll`               | Access token (employer or admin) | Enroll an employee in a policy.                                                          |
| DELETE | `/api/policies/{id}/enroll/{employee_id}` | Access token (employer or admin) | Unenroll an employee from a policy (soft-delete).                                        |

| POST   | `/api/feedback`                           | Access token          | Submit thumbs up/down (+ optional text) for a message.                                           |
| GET    | `/api/feedback/analytics`                 | Admin only             | Aggregated feedback stats for one employer.                                                       |
| GET    | `/api/admin/overview`                     | Admin only             | Top-level summary: query volume, active users, document count, avg satisfaction, cost this month. |
| GET    | `/api/admin/cost-dashboard`               | Admin only             | LLM spend: total, by model, by employer, by day. Filterable by employer/date range.                |
| GET    | `/api/admin/cost-dashboard/alerts`        | Admin only             | Employer/day pairs where spend exceeded the configured (or a query-param) threshold.               |
| GET    | `/api/admin/latency`                      | Admin only             | P50/P95/P99 response times, overall and broken down by model tier.                                 |
| GET    | `/api/admin/flagged-responses`            | Admin only             | Auto-flagged low-confidence responses. Filterable by employer/status.                              |
| PATCH  | `/api/admin/flagged-responses/{id}`       | Admin only             | Mark a flagged response reviewed, dismissed, or escalated.                                         |
| GET    | `/api/admin/guardrail-rejections`         | Admin only             | Blocked queries with rejection reasons. Filterable by employer/date range.                         |
| GET    | `/api/admin/unanswered-queries`           | Admin only             | Low-confidence-flagged queries (the structured proxy for "no answer found").                       |
| GET    | `/api/admin/topic-heatmap`                | Admin only             | Query volume by policy type, by day. Filterable by employer/date range.                            |
| GET    | `/api/admin/document-health`              | Admin only             | Documents with failed-ingestion/stale/zero-query-hit status.                                       |

**Standing convention decision**: like every other route file since Step 9.1, these return their Pydantic response model directly — not wrapped in an `APIResponse[T]` envelope (see `auth_routes.py`'s module docstring for the full reasoning).

Phase 9 (API routes) is complete. This table is kept current as endpoints are added.

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
