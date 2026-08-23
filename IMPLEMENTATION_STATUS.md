# Implementation Status

Tracks progress against `files/plan.md`, per the process defined in
`files/autopilot-prompt.md`. Updated after every completed step.

## Phase 0 — Git Repository & Delivery Workflow

### Step 0.1 — Initialize the repository and trunk — DONE

- Files: `.gitignore`, `.gitattributes`, `files/*.md` (bootstrap commit on
  `main` directly — the one exception to "never commit to main", since `main`
  didn't exist yet to branch from).
- Validation: `git push -u origin main` succeeded;
  `gh repo view --json defaultBranchRef` confirms `main` is the default
  branch.
- No PR for this step (bootstrapping paradox — see note above).

### Step 0.2 — Branch protection and ownership — DONE

- Files: `.github/CODEOWNERS`.
- Branch: `chore/branch-protection-and-codeowners` → PR #1 (squash-merged).
- Branch protection applied to `main` via `gh api`:
  `required_approving_review_count: 0` (solo-maintainer adjustment — GitHub
  disallows self-approval and there is no second reviewer yet),
  `require_code_owner_reviews: false` (same reason), `enforce_admins: true`,
  `required_linear_history: true`, `allow_force_pushes: false`,
  `allow_deletions: false`, `required_conversation_resolution: true`,
  `required_signatures: true`.
- Repo settings: squash-merge only (`mergeCommitAllowed`/`rebaseMergeAllowed`
  = false), `deleteBranchOnMerge: true`.
- Commit signing set up: SSH-based (`gpg.format=ssh`), local (non-global) git
  config, key registered via `gh ssh-key add --type signing`.
- Validation: `gh api repos/.../branches/main/protection` response confirmed
  all fields; `gh repo view --json deleteBranchOnMerge,squashMergeAllowed,...`
  confirmed merge settings.
- Known limitation: two-approval enforcement for CODEOWNERS paths (auth,
  tenant middleware, persistence adapters, migrations) is documented but not
  enforced (`required_approving_review_count: 0`) because this is a
  solo-maintained repo. Raise to 2 for those paths when a collaborator joins.

### Step 0.3 — Commit, branch, and PR conventions — DONE

- Files added: `commitlint.config.js`, `.pre-commit-config.yaml`,
  `.github/pull_request_template.md`,
  `.github/PULL_REQUEST_TEMPLATE/{feature,bugfix,refactor,chore,security,docs}.md`,
  `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config.yml}`,
  `.github/labeler.yml`, `CONTRIBUTING.md`, this file.
- Branch: `chore/commit-and-pr-conventions`.
- Labels created on GitHub: `type: feature`, `type: bug`, `type: hotfix`,
  `type: refactor`, `type: docs`, `type: chore`, `type: security`,
  `area: backend`, `area: frontend`, `area: infra`, `area: data`,
  `phase-0` … `phase-14`.
- Validation: `.pre-commit-config.yaml` and `commitlint.config.js` are config
  only at this point — `pre-commit` is not yet installed since no Python
  venv or backend/frontend code exists yet to lint. Both will be exercised
  for real starting Phase 1 once `backend/` and `frontend/` exist.

### Step 0.4 — Continuous integration pipelines — DONE

- Files: `.github/workflows/{ci,pr-lint,secret-scan,dependency-audit,docker-build,migration-check,release}.yml`.
- Branch: `ci/core-pipelines`.
- `ci.yml` has `backend-quality` and `frontend-quality` jobs; both guard on
  `backend/pyproject.toml` / `frontend/package.json` existing and no-op
  cleanly until Phase 1 / Phase 10 add real code, so PRs aren't blocked by
  checks for code that doesn't exist yet.
- `docker-build.yml` and `migration-check.yml` guard the same way on
  `backend/Dockerfile`/`frontend/Dockerfile` and `backend/alembic.ini`.
- `pr-lint.yml` validates the PR title (Conventional Commits) and branch name
  (`<type>/<scope>-<summary>`) against the same rules as `commitlint.config.js`
  and `CONTRIBUTING.md`.
- `secret-scan.yml` runs `gitleaks/gitleaks-action@v2` on every PR and push.
- `dependency-audit.yml` runs `pip-audit`/`npm audit`, guarded the same way,
  plus a weekly schedule.
- `release.yml` uses `googleapis/release-please-action@v4` (release-type
  `simple`) to derive the next semver from merged Conventional Commit types,
  generate `CHANGELOG.md`, and cut a GitHub Release with a tag on merge of
  its auto-generated release PR.
- **Known limitation**: tags/commits created by `release-please-action`
  (via `GITHUB_TOKEN`) are GitHub-API-created, not cryptographically signed
  with the SSH key set up in Step 0.2. They'll show as GitHub-verified
  (web-flow) but not "signed by rohangawhade's key." Getting true user/bot-key
  signed release tags out of Actions needs a dedicated bot signing key stored
  as a repo secret — deferred; flagging here rather than silently skipping it.
- Once this PR is open, its own checks (`pr-lint`, `secret-scan`,
  `dependency-audit`, `ci`, `docker-build`, `migration-check`) are the first
  real run of all seven workflows. After they pass, required status checks
  will be added to `main`'s branch protection to match.

**Phase 0 — Git Repository & Delivery Workflow: COMPLETE** (pending this PR's
merge).

## Phase 1 — Project Scaffolding & Infrastructure

### Step 1.1 — Initialize project skeleton — DONE

- Backend: `backend/pyproject.toml` (setuptools src-layout: `core`,
  `adapters`, `api`, `workers` importable as top-level packages, `main` as a
  top-level module — matches the bare-import style in
  `files/coding-standards.md`), full `core/`/`adapters/`/`api/`/`workers`
  directory skeleton with `__init__.py` per package, `backend/src/main.py`
  (minimal FastAPI app factory), `backend/tests/__init__.py`.
- Frontend: scaffolded with `npm create vite@latest -- --template react-ts`,
  then adjusted to match the plan/coding-standards exactly:
  - Pinned `react`/`react-dom` to `^18.3.1` (plan specifies React 18; latest
    Vite scaffolds installed React 19 by default).
  - Replaced the default `oxlint` lint setup with real ESLint (flat config,
    `typescript-eslint` + `react-hooks` + `react-refresh` + `eslint-config-prettier`)
    since `files/coding-standards.md` and `.pre-commit-config.yaml` (Step 0.3)
    both assume ESLint specifically.
  - Added `strict: true` to `tsconfig.app.json` — not on by default in the
    newest Vite template, required by coding-standards section 5.
  - Tailwind CSS v4 (latest) wired via `@tailwindcss/vite` + `@import
    "tailwindcss";` in `index.css`, plus `tailwind.config.ts` for explicit
    content globs (v4 auto-detects content, but the plan's folder structure
    names this file explicitly).
  - Removed the default template's boilerplate (logos, marketing copy,
    `App.css`) — replaced `App.tsx` with a one-line placeholder.
- `.env.example` — all env vars for app/database/redis/celery/Pinecone/LLM
  tiers/auth/CORS/frontend, matching `files/coding-standards.md` section 10
  and the model-routing config shown in `files/plan.md`.
- `Makefile` — install/dev/test/lint/format/typecheck/migrate/up/down/build/seed
  targets (Windows paths, since this is the actual dev machine).
- `README.md` — full structure per `files/coding-standards.md` section 14
  (What This Project Does, Architecture Overview, Features checklist, Tech
  Stack, collapsible setup sections, Project Structure, How It Works).
- Validation:
  - `pip install -e ".[dev]"` succeeded in `backend/.venv` (all deps resolve).
  - `python -c "from main import app"` → `PolicyPal 0.1.0`.
  - `ruff check .` / `ruff format --check .` / `mypy --strict src` all pass.
  - Frontend: `npm run lint` (ESLint) passes, `npm run build` (`tsc -b && vite
    build`) succeeds and produces a Tailwind-compiled CSS bundle.

### Step 1.2 — Docker Compose setup — DONE

- Files: `docker-compose.yml` (postgres, redis, backend, celery-worker,
  frontend, named volume, bridge network), `docker-compose.override.yml`
  (hot reload: `uvicorn --reload` + source mount for backend, `celery`
  concurrency=1 + source mount for celery-worker, `npm run dev` targeting the
  Dockerfile's `build` stage + source mount for frontend), `backend/Dockerfile`,
  `frontend/Dockerfile` (multi-stage: build then `serve` the static output).
- `backend/src/workers/celery_app.py` — a minimal, real (not mocked) Celery
  app with no tasks registered yet, so the `celery-worker` service has
  something genuine to run. Step 8.1 configures routing/retries/dead-letter
  handling on this same file.
- **Bug found and fixed during validation**: `.env.example`'s
  `REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`/`DATABASE_URL` use
  `localhost`, correct for host-based `make dev-backend` but wrong inside the
  Compose network (services reach each other by service name). Fixed by
  adding an `environment:` block to the `backend` and `celery-worker`
  services in `docker-compose.yml` that overrides just those four vars to
  use `postgres`/`redis` as hostnames — `env_file: .env` still supplies
  everything else (API keys, secrets, LLM config).
- Also fixed a `CPendingDeprecationWarning` from Celery by setting
  `broker_connection_retry_on_startup = True` explicitly.
- Validation: `docker compose build` succeeds for all three custom images;
  `docker compose up -d` brings up all 5 containers cleanly — postgres and
  redis report `healthy`, celery-worker logs `Connected to redis://redis:...`
  and `ready`, backend responds (404 on `/` — expected, no routes yet;
  confirms the server itself is up), frontend dev server responds 200 on
  `:5173`. Torn down with `docker compose down -v` after validation; the
  `.env` used for testing was a local, gitignored copy of `.env.example`
  (not committed).
- README.md updated with a working `docker compose up` quick-start.

### Step 1.3 — PostgreSQL + Alembic setup — DONE

- `backend/src/adapters/persistence/database.py` — async engine + session
  factory, `get_session()` FastAPI dependency. Reads `DATABASE_URL` directly
  from the environment (same pattern as `celery_app.py`) — Step 1.4's typed
  config supersedes this.
- `backend/src/adapters/persistence/models.py` — all 13 ORM tables from
  plan.md's Step 1.3 list: `Employer`, `Employee` (the login principal for
  all three roles — admin/employer/employee — distinguished by `role`;
  `employer_id` nullable only for `admin`), `Policy`, `EmployeePolicy`
  (enrollment), `Document`, `DocumentChunk`, `Conversation`, `Message`,
  `Feedback`, `LLMCostLog`, `RequestLatencyLog`, `FlaggedResponse`,
  `GuardrailRejection`. UUID primary keys, FK constraints, unique
  constraints (`employees.email`, `employee_policies.(employee_id,
  policy_id)`), and an indexed `employer_id` on every tenant-scoped table —
  denormalized directly onto `document_chunks`, `feedback`, `messages`, and
  `flagged_responses` (not just reachable via a join) so repository-level
  tenant scoping (coding-standards.md section 8) never needs one.
- `backend/alembic/` initialized; `env.py` rewritten for async SQLAlchemy
  (`async_engine_from_config` + `connection.run_sync`), reads
  `DATABASE_URL` from the environment, targets `Base.metadata` for
  autogenerate.
- First migration (`c66afd6b3aeb_initial_schema.py`) generated via
  `alembic revision --autogenerate`.
- **Two real bugs found and fixed during validation** (both documented
  inline in the migration file and in the README's Database Setup section):
  1. A model gap: `test_tenant_scoped_tables_have_an_employer_id_column`
     (written for this step) failed for `messages` — it only had
     `conversation_id`, not a denormalized `employer_id` like the other
     analytics/log tables. Fixed in `models.py`, migration regenerated.
  2. An Alembic/Postgres ENUM lifecycle bug: `op.create_table` auto-creates
     a named Postgres ENUM type on first use, but `op.drop_table` does
     **not** auto-drop it — so `alembic downgrade base` followed by
     `alembic upgrade head` failed with `type "..." already exists` for
     every one of the 6 enum types (not just `policy_type`, which is shared
     across two tables — all of them, including single-table enums).
     Fixed by defining each enum type once at module level
     (`create_type=False`) and explicitly `.create()`/`.drop()`-ing them in
     `upgrade()`/`downgrade()`. `migration-check.yml` now runs a
     downgrade-then-upgrade cycle specifically to catch this class of bug
     in future migrations.
- Validation: three full `upgrade head` → `downgrade base` → `upgrade head`
  cycles against a real Postgres 16 container, `alembic check` reports no
  drift after each, `\dt` confirms all 13 tables (+ `alembic_version`) with
  the right columns/types (`\d messages` spot-checked for `employer_id`).
  `ruff`, `ruff format`, `mypy --strict` all pass. New tests added:
  `tests/test_models.py` (table registry, tenant-scoping columns, timestamp
  mixin, enum vocabularies, unique constraints, relationship wiring,
  analytics-table columns) and `tests/test_database.py` (engine is async +
  asyncpg, session factory config, `get_session()` yields a real
  `AsyncSession`) — 100% coverage on both new files.
- README.md updated with a Database Setup section (bring-up, verify tables,
  how to generate future migrations, the ENUM lifecycle gotcha).

### Step 1.4 — Configuration management — DONE

- `backend/src/config.py` — nine typed, independently-instantiable Pydantic
  `BaseSettings` classes (own `env_prefix` each, per
  `files/coding-standards.md` section 10): `AppConfig`, `DatabaseConfig`,
  `RedisConfig`, `CacheConfig`, `CeleryConfig`, `PineconeConfig`,
  `LLMConfig`, `AuthConfig`, `CorsConfig`. `LLMConfig`/`AuthConfig` match
  the plan's four explicitly-named sections plus `DatabaseConfig`/
  `RedisConfig`/`PineconeConfig`/`CacheConfig`; `AppConfig` and
  `CorsConfig` added beyond that list since `.env.example` already declared
  `APP_*`/`CORS_*` vars with nowhere typed to live. Each class also reads
  the repo-root `.env` automatically (`_ENV_FILE`, resolved from
  `config.py`'s own path so it's correct regardless of CWD) for local
  host-based dev — real env vars (e.g. Docker Compose's `environment:`
  overrides from Step 1.2) still always win.
- Renamed `.env.example`'s `REDIS_CACHE_TTL_SECONDS` to `CACHE_TTL_SECONDS`
  so it cleanly maps to its own `CacheConfig` section instead of living
  under `RedisConfig`'s prefix.
- Refactored `database.py`, `celery_app.py`, and `alembic/env.py` (all three
  previously read `DATABASE_URL`/`CELERY_*` directly from `os.environ`, with
  a note in each saying Step 1.4 would supersede this) to use the new
  `config` module instead.
- **Real bug found and fixed**: `mypy --strict src` failed with `Source
  file found twice under different module names: "src.config" and
  "config"` once `celery_app.py`/`database.py` started doing
  `from config import ...`. Root cause: `backend/src/__init__.py`
  (created during Step 1.1's scaffolding) made mypy treat `src` as an
  importable package itself, so `src/config.py` got resolved both as
  `src.config` (via the `mypy --strict src` directory walk) and as bare
  `config` (via `mypy_path = "src"` resolving the import). Fixed by
  deleting `backend/src/__init__.py` — it was wrong for this src-layout
  from the start (`src/` is meant to be a path root, not a package; code
  imports `core.x`, `config`, `main` bare, never `src.x`), it just hadn't
  surfaced as a problem until something inside `src/` imported another
  top-level module by its bare name.
- Validation: `ruff`, `ruff format --check`, `mypy --strict src` all pass;
  new `tests/test_config.py` (module-level singleton types, sane
  non-secret defaults, env-prefix isolation between sections, `.env`-file
  isolation via pydantic-settings' `_env_file=None` override, CORS origin
  list parsing) — 100% coverage. Re-ran the full Step 1.3 migration
  validation (`alembic upgrade head` / `alembic check`) against a real
  Postgres container to confirm `alembic/env.py`'s refactor still works,
  and re-ran the full `docker compose up` stack end-to-end (backend,
  celery-worker, postgres, redis, frontend) to confirm the config refactor
  still correctly picks up Compose's `redis://redis:...` overrides.
- README.md updated (API Keys & Model Configuration section now describes
  the typed config layer; Features checklist also caught up — Postgres/
  Alembic was done in 1.3 but the checkbox was missed then).

### Step 1.5 — Health check endpoints — DONE

- `backend/src/api/routes/health_routes.py`: `GET /health` (liveness,
  always 200, no dependency checks) and `GET /ready` (readiness — checks
  PostgreSQL via a real `SELECT 1`, Redis via a real `PING`; Pinecone via a
  real `list_indexes()` call only if `PINECONE_API_KEY` is configured,
  else reported as `not_configured` and not counted as a failure). Returns
  HTTP 503 (not just an `"error"` body) when not ready, so orchestrators
  keying off status code behave correctly. Kept dependency-light on
  purpose — no repository ports, no domain services — so it works even if
  the rest of the app is broken.
- Wired into `main.py` via `app.include_router(health_routes.router)`.
- `docker-compose.yml`'s `backend` service healthcheck (deferred since
  Step 1.2, when `/health` didn't exist yet) now targets it.
- Validation: `ruff`, `ruff format --check`, `mypy --strict src` all pass
  (added a targeted mypy override for `pinecone.*`, same situation as
  `celery.*` in Step 1.2 — no py.typed marker or reliable stubs). New
  `tests/test_health_routes.py` — unit tests for each `_check_*` helper
  (success and failure paths, including the real Pinecone-configured
  branch, mocked) plus integration tests through `TestClient` for both
  200/ready and 503/not-ready response shapes — 100% coverage.
  **Additionally verified against the real stack, not just mocks**: ran
  the actual app against live Postgres + Redis containers and confirmed
  `/health` and `/ready` both report `ok`; stopped the Postgres container
  and confirmed `/ready` correctly flips to HTTP 503 with
  `"database": "error"`; brought up the full `docker compose up` stack and
  confirmed `docker compose ps` shows the backend as `(healthy)`.

**Phase 1 — Project Scaffolding & Infrastructure: COMPLETE**.

## Phase 2 — Core Domain & Ports

### Step 2.1 — Domain models — DONE

- `backend/src/core/domain/{employer,employee,policy,document,conversation,feedback,analytics}.py`
  — pure Pydantic `BaseModel`s, zero imports from FastAPI/SQLAlchemy/any
  adapter (verified: only stdlib + pydantic imports, plus one
  domain-to-domain import of `PolicyType` in `document.py`, which is fine).
  Mirrors the 13 ORM tables from Step 1.3 exactly, matching plan.md's Step
  2.1 model list (`Enrollment` — plan's name — lives in `policy.py`, next
  to `Policy`, since the plan's folder tree doesn't list a separate
  `enrollment.py`/`message.py` file).
  - Every model sets `model_config = ConfigDict(from_attributes=True)` so
    Phase 3's repository adapters can do `Employer.model_validate(orm_row)`
    without hand-written field-by-field mapping.
  - `id`/timestamp fields have sensible `default_factory` values (`uuid4`,
    `datetime.now(UTC)`) so domain objects are directly constructible
    before persistence, not just after loading from the DB.
  - `Employee` includes `hashed_password` (needed by the future
    `AuthService`) — this is domain data, not a persistence detail; API
    layers must remember to exclude it from response schemas when that
    matters (Phase 9).
- **Real bug found and fixed**: used `datetime.utcnow()` for every
  timestamp default (7 files) — deprecated in Python 3.12
  (`DeprecationWarning`, scheduled for removal). Only surfaced because
  `pytest` runs on 3.12 and warnings were visible in the test summary; the
  code itself worked fine, it just wasn't clean. Fixed by switching to
  `datetime.now(UTC)` everywhere, **and** added
  `filterwarnings = ["error::DeprecationWarning", "error::PendingDeprecationWarning"]`
  to `pyproject.toml`'s pytest config so this class of bug fails CI
  immediately in future steps instead of accumulating silently. Confirmed
  no other deprecation warnings exist anywhere in the current dependency
  set after adding this.
- Validation: `ruff`, `ruff format --check`, `mypy --strict src` all pass.
  New `tests/test_domain_models.py` — one focused test per model
  (construction, defaults, enum values, a validation-error case for a
  missing required field, and one test proving `from_attributes=True`
  actually works against an ORM-shaped object) — 100% coverage, zero
  warnings.

### Step 2.2 — Port interfaces (ABCs) — DONE

- `backend/src/core/ports/{llm_port,vector_store_port,event_bus_port,cache_port,document_processor_port,repository_ports}.py`
  — every ABC from plan.md's Step 2.2 list. `repository_ports.py` uses a
  generic `RepositoryPort[T]` base (get/create/update/delete) per
  `files/coding-standards.md` section 5's "use TypeVar and Generic for
  generic repository interfaces", with one subclass per entity adding its
  own query methods (`EmployeeRepository.get_by_email`,
  `DocumentRepository.get_latest_version` for Step 7.1's version tracking,
  `DocumentChunkRepository.deactivate_by_document` for Step 7.2's soft
  delete, etc.), plus a combined `AnalyticsRepository` for the four
  observability tables (written together fire-and-forget, read together by
  the admin dashboard — one port, not four, per how they're actually used).
- `VectorStorePort`/`EventBusPort` needed small supporting types that
  don't belong in `core/domain/` (they're port-contract shapes, not
  entities): `VectorRecord`/`VectorMatch` (frozen dataclasses) defined
  directly in `vector_store_port.py`, and an `EventHandler` type alias in
  `event_bus_port.py`.
- **Prerequisite added ahead of Step 2.3**: `EventBusPort.publish()` needs
  a type to publish against, but concrete domain events don't exist until
  Step 2.3. Added a minimal `core/domain/events.py` with just the
  `DomainEvent` base (frozen, `kw_only=True` — avoids the classic
  dataclass-inheritance trap where a subclass's required field can't
  follow a base field that has a default) — a small, strictly-required
  prerequisite per `files/autopilot-prompt.md`'s execution rules. Step 2.3
  extends this same file with the concrete event classes.
- Real subtlety caught before it became a bug: `LLMPort.generate_stream`
  is meant to be implemented as an async generator (`async def ...: yield
  token`), which genuinely requires `async def` in Python — an earlier
  draft declared the abstract method with plain `def` on the theory that
  "callers shouldn't await it", which is correct about the *calling*
  convention (`async for`, never `await`) but wrong about how async
  generators are *declared*. Fixed before commit by giving the abstract
  stub a real `yield` so it's unambiguously typed as `AsyncIterator[str]`
  the same way a real implementation would be.
- Validation: `ruff`, `ruff format --check`, `mypy --strict src` all pass.
  New `tests/test_ports.py` (LLM/VectorStore/EventBus/Cache/
  DocumentProcessor — each proven instantiable only via a complete
  concrete subclass, plus a frozen-dataclass immutability check for
  `VectorRecord`/`VectorMatch`) and `tests/test_repository_ports.py`
  (generic base can't be instantiated directly, an intentionally
  *incomplete* subclass still can't be instantiated, `AnalyticsRepository`
  exercised end-to-end) — 100% coverage, zero warnings, 59 tests total.

### Step 2.3 — Domain events — DONE

- `backend/src/core/domain/events.py` extended with all 11 concrete event
  classes from plan.md's Step 2.3 list: `DocumentUploadedEvent`,
  `DocumentProcessedEvent`, `DocumentEmbeddedEvent`,
  `DocumentVersionReplacedEvent`, `EmployerCreatedEvent`,
  `EmployeeEnrolledEvent`, `ChatMessageReceivedEvent`,
  `ChatResponseGeneratedEvent`, `FeedbackReceivedEvent`,
  `LowConfidenceResponseEvent`, `GuardrailRejectionEvent`. Each is a
  frozen, `kw_only=True` dataclass subclassing `DomainEvent` (added in
  Step 2.2) with its own fixed `event_type` default (re-declaring the
  base's `event_type` field with a concrete default), so callers never
  pass it by hand — e.g. `DocumentUploadedEvent(document_id=...,
  employer_id=..., title=...)` is enough.
- Verified before writing the full test suite that overriding a
  no-default base field with a defaulted one in a `kw_only=True` subclass,
  while also adding new required fields, actually constructs correctly —
  ran it directly rather than assuming the dataclass-inheritance mechanics
  work as expected.
- Validation: `ruff`, `ruff format --check`, `mypy --strict src` all pass.
  New `tests/test_domain_events.py` — one test per event class (fixed
  `event_type`, payload fields, a frozen/immutability check, inherited
  `timestamp`) — 100% coverage, zero warnings, 72 tests total across the
  whole suite.

## Operational fix — release-please was silently failing since PR #6

**What happened**: `release.yml` (added Step 0.4) has been failing on
every push to `main` since PR #6 merged (2026-08-23 14:02) — 5 failures
in a row (#6-#10), completely unnoticed. Root cause: the repo-level
setting "Allow GitHub Actions to create and approve pull requests" was
off (GitHub's default for new repos), so `release-please-action` could
authenticate and compute the next version fine, but failed the instant it
tried to actually *open* its release PR: `GitHub Actions is not permitted
to create or approve pull requests.` PRs #3-#5 had shown green only
because release-please found no user-facing commits yet and skipped
opening a PR entirely — the failure path was never exercised until real
`feat`/`fix` commits started landing.

**Why this was missed**: every validation pass in Phases 0-2 checked the
7 PR-triggered required status checks (via `gh pr checks`) obsessively,
but `release.yml` only triggers on push to `main` — a separate event
that happens *after* merge, which was never independently watched. This
is a real gap in the validation process, not a one-off — checking what
gates the merge is not the same as checking what the merge itself
triggers.

**Caught by**: the user directly asking to inspect a specific failed
Action run and report the cause honestly.

**Fixed**: `gh api --method PUT repos/.../actions/permissions/workflow -f
default_workflow_permissions=read -F can_approve_pull_request_reviews=true`
(user-approved — this write is classifier-blocked, like `gh pr merge`).
Verified by re-running the exact failed job (`gh run rerun`), not just
assuming the setting change worked — it succeeded and opened a real
release PR proposing `v1.0.0`.

**Follow-on decision**: a first release at `v1.0.0` is wrong for a
project mid-Phase-2 of 14. Closed that PR unmerged, added
`release-please-config.json` + `.release-please-manifest.json` (seeding
`"." : "0.1.0"` as the baseline) so future runs propose sane pre-1.0
versions instead. `release.yml` updated to reference these files instead
of the inline `release-type: simple` input.

**Standing gap, not yet closed**: nothing currently watches push-to-`main`
workflow results automatically. Until that's addressed, checking
`gh run list --repo rohangawhade/policy-chatbot --workflow=release.yml`
(or the Actions tab) after merges is a manual step worth doing
periodically, not just when explicitly asked.

**Phase 2 — Core Domain & Ports: COMPLETE**.

## Phase 3 — Infrastructure Adapters

### Step 3.1 — In-memory event bus adapter — DONE

- `backend/src/adapters/event_bus/in_memory_event_bus.py` —
  `InMemoryEventBus` fulfilling `EventBusPort` (added Step 2.2). Keyed by
  `event_type` string (not the event class) so handlers can subscribe
  without importing every concrete event class. Supports both sync and
  async handlers (`inspect.isawaitable(result)` on the handler's return
  value decides whether to `await` it) per plan.md's Step 3.1
  requirement. A handler that raises is caught, logged via
  `structlog.exception` (with the event type and handler name), and does
  not prevent other subscribed handlers from running — matches
  `files/coding-standards.md` section 12's "analytics logging must never
  block the main request" principle, generalized to any handler since the
  bus has no way to know which handlers are analytics vs. not.
  `unsubscribe()` on an unknown event type or a handler not currently
  subscribed logs a warning and returns rather than raising (no caller
  currently needs unsubscribe to be strict).
  Docstring explicitly states the swap-for-Kafka intent from plan.md's
  Step 3.1 ("Swap this for `KafkaEventBus`... zero core logic changes").
- This is the first adapter in the codebase to use `structlog`
  (declared as a dependency since Step 0.1/pyproject.toml, unused until
  now) — used at its default configuration (no `structlog.configure()`
  call exists yet anywhere in the app); Step 13's structured-logging setup
  (JSON in prod, pretty-print in dev, correlation_id/employer_id/user_id
  on every entry) is a cross-cutting concern from `coding-standards.md`
  section 13, not a dedicated plan.md step — will be wired centrally
  whichever step first needs request-scoped context (likely Phase 5's
  auth/tenant middleware).
- Validation: `ruff check`, `ruff format --check`, `mypy --strict src` all
  pass. New `tests/test_in_memory_event_bus.py` — sync handler dispatch,
  async handler dispatch (awaited), multiple handlers called in
  subscription order, handlers for a different event type not invoked,
  publish with zero subscribers doesn't raise, a failing sync handler and
  a failing async handler each don't block sibling handlers, unsubscribe
  removes a handler so it stops receiving events, unsubscribe on an
  unknown event type or an unregistered handler doesn't raise — 100%
  coverage on the new file, zero warnings, 83 tests passing across the
  whole suite (up from 72).

### Step 3.2 — LiteLLM adapter — DONE

- `backend/src/adapters/llm/litellm_adapter.py` — `LiteLLMAdapter`
  fulfilling `LLMPort`. `generate()`/`generate_stream()` call
  `litellm.acompletion()` (the async entry point — plan.md says
  `litellm.completion()`, but `coding-standards.md` section 9 requires
  every I/O-bound call to be genuinely `async`, and `acompletion()` is
  LiteLLM's async equivalent); `embed()` calls `litellm.aembedding()`.
  Model name is 100% caller-driven (`model=` param on every call,
  ultimately sourced from `LLMConfig.cheap_model`/`powerful_model`/
  `embedding_model` set up in Step 1.4) — the adapter itself has no
  opinion on model tier.
  - `tenacity` retry with exponential backoff on `APIConnectionError`,
    `Timeout`, `RateLimitError`, `ServiceUnavailableError` only (never on
    e.g. an auth/bad-request error, which fails identically every time):
    3 attempts for `generate`/`generate_stream`, 2 for `embed`, per
    `coding-standards.md` section 11's explicit per-call-type limits.
    Every retry logs the attempt number and error via `structlog`
    (`before_sleep` hook).
  - `generate_stream()`'s retry covers only *establishing* the stream
    (a private `_start_stream` helper) — once tokens have reached the
    caller, a transparent retry would silently replay or duplicate
    output, so a mid-stream failure propagates as-is instead.
  - `litellm.acompletion()` is typed to return
    `Union[ModelResponse, CustomStreamWrapper]` regardless of the
    `stream=` value passed (no `@overload`s), and `ModelResponse.choices`
    is itself typed `list[Union[Choices, StreamingChoices]]` — both
    narrowed via explicit `isinstance` checks (raising `TypeError` on a
    mismatch) rather than an `# type: ignore`, so `mypy --strict` passes
    with zero suppressions in this file.
- `backend/src/adapters/llm/mock_llm_adapter.py` — `MockLLMAdapter`
  fulfilling `LLMPort` with no network calls: `generate`/`generate_stream`
  return/stream a fixed canned string; `embed()` derives each vector
  deterministically from a SHA-256 hash of the input text, so retrieval/
  similarity tests built on it later get stable, reproducible results
  without a real embedding model.
- **Two real bugs found and fixed during validation, both in test
  infrastructure rather than the adapter itself**:
  1. `import litellm` alone (even before any of our code runs) raises a
     `PydanticDeprecatedSince20` `DeprecationWarning` (a class-based
     `Config` still used somewhere inside litellm 1.63.x's own
     `types/llms/openai.py`) and, separately, an
     `importlib.resources.open_text` `DeprecationWarning` under Python
     3.12 (`litellm/utils.py`) — both promoted to hard errors by
     `pyproject.toml`'s `filterwarnings`, breaking test collection the
     instant any test imports `litellm`. Neither is our code. Fixed with
     `backend/tests/conftest.py`, which imports `litellm` once up front
     inside `warnings.catch_warnings()`/`simplefilter("ignore")` — the
     module is cached in `sys.modules` afterward, so every later
     `import litellm` (in the adapter or in test files) is a silent
     no-op that can't re-trigger the warning.
  2. `litellm/__init__.py` unconditionally calls `dotenv.load_dotenv()`
     at import time, which loads the repo-root `.env` file straight into
     the real process `os.environ` — indistinguishable afterward from a
     genuinely exported env var, for the rest of the process. This
     silently broke `test_config.py`'s `_env_file=None` isolation
     (`PineconeConfig(_env_file=None).api_key` started returning `""`
     instead of `None`, picked up from the local `.env`'s empty
     `PINECONE_API_KEY=` line) the moment `conftest.py` imported
     `litellm` for fix #1. Fixed by snapshotting `os.environ` before the
     import and deleting exactly the keys `dotenv.load_dotenv()` added
     (real env vars are never touched either way — `load_dotenv()`
     defaults to not overriding a value that's already set). Production
     impact is judged benign for the same reason (real env vars, e.g.
     Docker Compose `environment:` overrides, already win), but this is
     a real latent side effect worth knowing about if `litellm` is ever
     imported before `config.py` reads an env var somewhere unexpected —
     flagging here rather than silently working around it only in tests.
- **Validated with mocks only, not against a real provider**: both
  `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are empty in the local `.env`
  — no real credentials are available in this environment. Every
  `LiteLLMAdapter` test monkeypatches `litellm.acompletion`/
  `litellm.aembedding` directly (constructing real `litellm` response
  objects — `ModelResponse`, `Choices`, `Message`, `ModelResponseStream`,
  `StreamingChoices`, `Delta`, `EmbeddingResponse` — rather than raw
  dicts, so the tests still catch a real shape mismatch). No live API
  call has been made. Revisit with a real smoke test once a provider key
  is available (`MockLLMAdapter` is the deliberate stand-in for local
  dev/testing until then, per plan.md's explicit ask for one).
- Validation: `ruff check`, `ruff format --check`, `mypy --strict src`
  all pass with zero suppressions in the new files. New
  `tests/test_litellm_adapter.py` (success path, `None`-content edge
  case, retry-then-succeed, retry-exhaustion-then-reraise, non-retryable
  error short-circuits after one attempt, wrong-response-type guards for
  both `generate` and the embedded `Choices`/`StreamingChoices` check,
  streaming token extraction skipping empty deltas, streaming
  retry-then-succeed, embed happy path, embed's 2-attempt retry ceiling,
  embed wrong-response-type guard) and `tests/test_mock_llm_adapter.py`
  (non-empty deterministic `generate`, `generate_stream` tokens joining
  back to the same canned response, `embed` one-vector-per-input in
  order, deterministic per-text, distinct across different texts,
  correct dimensionality) — 100% coverage on both new adapter files, 105
  tests passing across the whole suite (up from 83), zero warnings.
  An `asyncio.sleep` patch (autouse fixture) removes real backoff delay
  from the retry tests so they run in milliseconds, not seconds.

## Environment / tooling notes for future steps

- **gh CLI**: installed via `winget install --id GitHub.cli`, authenticated
  as `rohangawhade` (scopes: `repo`, `read:org`, `gist`,
  `admin:ssh_signing_key`). `gh.exe` is copied to `~/bin/gh.exe` (already on
  Git Bash's `PATH`) so commands can be invoked as plain `gh ...` — this
  matters because the `gh pr merge`/`gh pr close` permission rule only
  matches commands that literally start with that text.
- **PR merges**: the auto-mode classifier hard-blocks `gh pr merge`/
  `gh pr close` by default and blocks any attempt to self-modify
  `.claude/settings.*` permissions. The user added an explicit allow rule to
  `.claude/settings.local.json`. Per-PR: I still ask for a go-ahead in chat
  before merging (user's stated preference), then run `gh pr merge`.
- **Python**: 3.12.6 available (`python`/`py`). Project venv created at
  `backend/.venv` per the autopilot instruction to use a project-local env,
  not the global interpreter. All backend commands in the Makefile invoke it
  by full path (Windows layout: `.venv/Scripts/*.exe`).
- **Node**: v22.12.0 / npm 11.12.1 available.
- **Commit signing**: SSH-based, configured locally (per-repo, not global) —
  see `CONTRIBUTING.md` "Signed commits" section for the reusable setup
  steps.
- **Docker Desktop**: installed but was not running at the start of Phase 1;
  started via `Docker Desktop.exe` and polled until `docker info` succeeded
  (~1-2 min cold start). Needed before any `docker compose` command works.

## Next recommended step

Merge the Step 3.2 PR, then continue Phase 3 — Infrastructure Adapters:
Step 3.3 (`PineconeAdapter` implementing `VectorStorePort`, one namespace
per employer), Step 3.4
(`RedisCacheAdapter` + `InMemoryCacheAdapter` implementing `CachePort`),
Step 3.5 (PostgreSQL repository adapters implementing every port in
`repository_ports.py`, Unit of Work pattern), Step 3.6 (document processor
adapters — PDF/DOCX/XLSX/XML — implementing `DocumentProcessorPort` via a
`ProcessorFactory`).
