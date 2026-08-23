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

Merge the Step 1.4 PR, then continue Phase 1 with Step 1.5 —
health/readiness probes (`GET /health`, `GET /ready`; also lets
`docker-compose.yml` add the backend healthcheck it's currently missing,
closing out Phase 1).
