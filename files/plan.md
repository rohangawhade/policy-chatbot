# PolicyPal — Implementation Plan

## RAG-Powered Employee Benefits Chatbot

---

## Project Overview

PolicyPal is a production-grade, multi-tenant RAG chatbot that allows employees and employers to query their enrolled benefit policies (health, dental, vision, etc.). The system is domain-restricted — it only answers policy-related questions scoped to the authenticated user's data.

---

## Finalized Tech Stack

| Layer                  | Technology                                      |
| ---------------------- | ----------------------------------------------- |
| Backend API            | FastAPI (async, Python 3.11+)                   |
| LLM Gateway            | LiteLLM (unified interface for any LLM)         |
| RAG Pipeline           | Custom-built (no LangChain/LlamaIndex)          |
| Vector Database        | Pinecone                                        |
| Relational Database    | PostgreSQL (via SQLAlchemy async + Alembic)      |
| Authentication         | OAuth2 + JWT (python-jose, passlib)             |
| Background Jobs        | Celery + Redis                                  |
| Caching                | Redis (query response cache)                    |
| Document Parsing       | unstructured, PyMuPDF, python-docx, openpyxl    |
| Chunking               | Hybrid: semantic + metadata-aware               |
| Frontend               | React 18 + TypeScript + Tailwind CSS            |
| Streaming              | Server-Sent Events (SSE)                        |
| Containerization       | Docker Compose                                  |
| RAG Evaluation         | RAGAS framework + golden dataset + user feedback |
| Data Sources           | Real gov PDFs + synthetic employer docs          |
| Version Control        | Git + GitHub (trunk-based, short-lived branches) |
| Commit Convention      | Conventional Commits + Semantic Versioning       |
| CI/CD                  | GitHub Actions (lint, typecheck, test, build)    |
| Code Quality Gates     | pre-commit hooks, CODEOWNERS, required reviews   |

---

## Architecture Principles

- **Hexagonal / Ports & Adapters**: Core business logic has zero dependency on frameworks, databases, or external services. All external interactions happen through abstract ports (interfaces) with swappable adapters.
- **Event-Driven Ready**: An in-memory event bus handles all inter-module communication today. Swapping to Kafka later means writing one new adapter — zero core logic changes.
- **Repository Pattern**: All data access goes through repository interfaces. PostgreSQL adapter today, swap to DynamoDB tomorrow without touching a single service file.
- **Strategy Pattern for LLMs**: LiteLLM already abstracts models, but our own `LLMPort` interface wraps even LiteLLM — so the entire LLM layer is replaceable.
- **Factory Pattern for Document Processing**: Each file type (PDF, DOCX, XML, XLSX) has its own processor. Adding a new format = adding one class, zero changes elsewhere.
- **Domain-Driven boundaries**: Employer, Employee, Policy, Document, Conversation — each is a bounded context with its own models, services, and repositories.
- **Multi-Model Routing**: A query complexity router sends simple questions to cheap/fast models and complex reasoning to powerful models, with automatic fallback if a model tier is unavailable.
- **Admin Observability Layer**: Every LLM call, retrieval, guardrail rejection, and user interaction is logged to PostgreSQL as structured analytics events. The admin dashboard reads from these — no separate analytics infra needed.
- **Trunk-Based Delivery**: `main` is always releasable and never receives direct commits. Every unit of work lands on a short-lived typed branch, ships through a reviewed pull request, and is squash-merged. Work in progress is hidden behind config flags, not long-lived branches.

---

## Git Workflow, Branching & Pull Request Strategy

This is the delivery contract for the project. Every step in every phase below ships through this workflow. No code reaches `main` any other way.

### Branching Model — Trunk-Based Development

`main` is the single long-lived trunk. It is protected, always green, and always deployable. Feature branches are cut from `main`, live for hours to a few days, and are deleted immediately after merge. There are no long-lived `develop`, `release`, or `staging` branches — those cause merge hell and are avoided by every high-velocity product org.

```
main ──●────────────●────────────●────────────●────────────●──→  (protected, always releasable)
       │            ▲            ▲            ▲            ▲
       │            │            │            │            │
       └─ feat/…────┘            │            │            │      squash-merge via PR
                    └─ fix/…─────┘            │            │
                                 └─ chore/…───┘            │
                                              └─ hotfix/…──┘      fast-track, then tag release
```

### Branch Naming Convention

Format: `<type>/<scope>-<short-kebab-summary>`

The `<type>` prefix is what differentiates the change class. It drives the PR template, the PR label, the CI jobs that run, the changelog section, and the version bump.

| Type       | Branch prefix | Used for                                                        | Example branch                          | Version bump |
| ---------- | ------------- | --------------------------------------------------------------- | --------------------------------------- | ------------ |
| Feature    | `feat/`       | New user-facing capability or new module                         | `feat/rag-streaming-generation`         | MINOR        |
| Bug fix    | `fix/`        | Correcting broken behavior in existing code                      | `fix/sse-stream-not-closing`            | PATCH        |
| Hotfix     | `hotfix/`     | Urgent production defect, fast-tracked review                    | `hotfix/jwt-expiry-bypass`              | PATCH        |
| Refactor   | `refactor/`   | Internal restructuring, no behavior change                       | `refactor/extract-chunker-pipeline`     | none         |
| Performance| `perf/`       | Measurable latency, cost, or memory improvement                  | `perf/batch-embedding-calls`            | PATCH        |
| Tests      | `test/`       | Adding or improving tests only                                   | `test/guardrails-edge-cases`            | none         |
| Docs       | `docs/`       | README, plan, ADRs, API docs                                     | `docs/admin-analytics-endpoints`        | none         |
| Chore      | `chore/`      | Dependency bumps, tooling, scaffolding, config                   | `chore/bump-fastapi-0-115`              | none         |
| Build      | `build/`      | Dockerfiles, Compose, packaging                                  | `build/compose-healthchecks`            | none         |
| CI         | `ci/`         | GitHub Actions workflows and pipeline config                     | `ci/add-ragas-eval-job`                 | none         |
| Security   | `security/`   | Vulnerability remediation, auth hardening                        | `security/tenant-isolation-audit`       | PATCH        |
| Revert     | `revert/`     | Reverting a previously merged PR                                 | `revert/pr-142-semantic-chunker`        | PATCH        |

Rules:
- Lowercase, kebab-case, no spaces, no personal names, no `my-branch` or `temp`.
- Include the issue/ticket ID when one exists: `fix/PP-231-duplicate-chunk-upsert`.
- One branch = one logical change. If a PR needs two summaries, it should be two PRs.
- Maximum branch lifetime: 3 days. Rebase onto `main` daily to avoid drift.

### Commit Convention — Conventional Commits

Every commit message follows the Conventional Commits specification. This is what enables automated changelog generation, semantic version bumping, and instant `git log` readability.

```
<type>(<scope>): <imperative summary under 72 chars>

<optional body: what changed and why, wrapped at 100 chars>

<optional footer: BREAKING CHANGE: …, Closes #123, Refs PP-231>
```

Examples:

```
feat(rag): stream generated tokens over SSE with source citations
fix(auth): reject refresh tokens issued before a password change
perf(embedding): batch chunk embeddings into groups of 96
refactor(chunking): extract metadata enrichment into its own stage
docs(readme): document admin analytics endpoints
chore(deps): bump litellm to 1.63.11
test(guardrails): cover ambiguous off-topic classification cases
security(tenant): enforce employer_id filter in every repository query
```

Rules:
- Allowed scopes mirror the module tree: `core`, `domain`, `ports`, `rag`, `router`, `guardrails`, `auth`, `tenant`, `chunking`, `embedding`, `vectorstore`, `cache`, `eventbus`, `persistence`, `api`, `admin`, `workers`, `frontend`, `chat`, `eval`, `docker`, `ci`, `deps`.
- Use the imperative mood: "add", not "added" or "adds".
- Breaking changes require a `BREAKING CHANGE:` footer or a `!` after the type: `feat(api)!: rename employer routes`.
- No commits with messages like `wip`, `fix stuff`, `.`, or `update`. Squash them before opening the PR.
- Never commit secrets, `.env` files, credentials, generated documents, or `node_modules`.

### Pull Request Standards

PR title uses the exact same Conventional Commits format as commits, because the PR title becomes the squash-merge commit message on `main`.

Every PR must include:
- **Type label**, applied automatically from the branch prefix: `type: feature`, `type: bug`, `type: hotfix`, `type: refactor`, `type: docs`, `type: chore`, `type: security`.
- **Phase label** tying it back to this plan: `phase-1` … `phase-14`.
- **Description** covering: what changed, why, how it was validated, and screenshots for UI work.
- **Linked issue** using a closing keyword (`Closes #123`).
- **Risk and rollback note** for anything touching auth, tenancy, migrations, or the RAG pipeline.
- **Checklist** confirming tests added, README updated, no secrets committed, and architecture boundaries respected.

PR sizing: target under 400 changed lines. Anything larger is split into stacked PRs. Large PRs do not get real reviews.

### PR Templates by Change Type

Separate templates live in `.github/PULL_REQUEST_TEMPLATE/` so each change class asks for the right evidence:

| Template            | Applies to                | Required sections beyond the defaults                                     |
| ------------------- | ------------------------- | ------------------------------------------------------------------------- |
| `feature.md`        | `feat/`                   | User-facing behavior, config flags added, test plan, rollout plan          |
| `bugfix.md`         | `fix/`, `hotfix/`         | Root cause, reproduction steps, regression test proving the fix            |
| `refactor.md`       | `refactor/`, `perf/`      | Behavior-unchanged statement, before/after benchmarks for `perf/`          |
| `chore.md`          | `chore/`, `build/`, `ci/` | Dependency diff, security advisory check                                   |
| `security.md`       | `security/`               | Threat description, blast radius, disclosure handling                      |
| `docs.md`           | `docs/`                   | Which docs changed and why they were stale                                 |

### Merge Policy

- **Squash and merge** is the only allowed strategy for `feat/`, `fix/`, `chore/`, `docs/`, `test/`, and `refactor/` branches. One PR becomes exactly one commit on `main`, keeping history linear and bisectable.
- **Rebase, never merge commits**, when updating a branch from `main`. No `Merge branch 'main' into …` noise.
- Branches are deleted automatically on merge.
- Force-push is allowed on your own feature branch only, never on `main`.

### Branch Protection Rules on `main`

- Direct pushes blocked. Everything goes through a PR.
- Minimum one approving review; two for changes to auth, tenant isolation, or database migrations, enforced through `CODEOWNERS`.
- All required status checks must pass: backend lint, backend typecheck, backend tests, frontend lint, frontend typecheck, frontend build, Docker build, secret scan.
- Branch must be up to date with `main` before merging.
- Conversations must be resolved before merging.
- Linear history required. Force-push and branch deletion on `main` are blocked for everyone.
- Signed commits required.

### CI Pipeline (GitHub Actions)

Runs on every PR and on every push to `main`:

1. `backend-quality` — `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` with coverage threshold.
2. `frontend-quality` — `eslint`, `tsc --noEmit`, `vite build`.
3. `docker-build` — builds backend and frontend images to catch broken Dockerfiles.
4. `migration-check` — verifies Alembic migrations apply cleanly to an empty PostgreSQL service container and that no model drift exists.
5. `secret-scan` — gitleaks scan on the diff; the job fails the PR on any hit.
6. `dependency-audit` — `pip-audit` and `npm audit` for known vulnerabilities.
7. `rag-eval` — runs the RAGAS golden-dataset evaluation, triggered only when chunking, prompt, retrieval, or model-routing files change. Fails the PR if any metric regresses below its configured threshold.

### Local Pre-Commit Hooks

Installed via `pre-commit`, so broken code never leaves the machine:
- `ruff` lint and format on staged Python files.
- `mypy` on the backend `src` tree.
- `eslint` and `prettier` on staged frontend files.
- `commitlint` enforcing the Conventional Commits format on the commit message.
- `gitleaks` blocking secrets before they are ever committed.
- Blocked file patterns: `.env`, `*.pem`, `*.key`, `data/gov_pdfs/*`, `data/synthetic/*`.

### Release Management

- Semantic Versioning: `MAJOR.MINOR.PATCH`, derived automatically from the Conventional Commit types merged since the last tag.
- Every release is an annotated, signed tag on `main`: `v0.4.0`.
- `CHANGELOG.md` is generated from commit history and grouped into Features, Bug Fixes, Performance, Security, and Documentation.
- Hotfixes branch from the release tag when `main` has already moved ahead, then get merged back into `main` immediately so the fix is never lost.

### Per-Step Delivery Loop (applies to every step in every phase)

Every implementation step below is a self-contained delivery unit. The loop is:

```
1. git checkout main && git pull --rebase origin main
2. git checkout -b <type>/<scope>-<summary>        ← typed branch, never work on main
3. Implement the step. Add tests. Update README.md.
4. Run the local gates: ruff, mypy, pytest, eslint, tsc.
5. git add -p && git commit -m "<type>(<scope>): <summary>"   ← Conventional Commits
6. git push -u origin <branch>                     ← push the feature branch, never main
7. Open a PR against main using the template matching <type>.
   Apply the type label and the phase label. Link the issue.
8. CI runs. Fix anything red. Address review comments with follow-up commits.
9. Squash-merge into main. Delete the branch.
10. Tag a release when a phase completes.
```

No step is considered done until its branch is merged into `main` through a green, reviewed PR.

### Phase-to-Branch Mapping

Each phase groups related branches under a consistent scope so history reads as a coherent story.

| Phase | Typical branch types                 | Example branch                          |
| ----- | ------------------------------------ | --------------------------------------- |
| 0     | `chore/`, `ci/`, `docs/`             | `chore/git-workflow-setup`              |
| 1     | `chore/`, `build/`, `feat/`          | `build/docker-compose-services`         |
| 2     | `feat/`                              | `feat/core-domain-models`               |
| 3     | `feat/`                              | `feat/pinecone-vector-store-adapter`    |
| 4     | `feat/`, `perf/`                     | `feat/semantic-chunker`                 |
| 5     | `feat/`, `security/`                 | `security/tenant-context-isolation`     |
| 6     | `feat/`                              | `feat/rag-streaming-generation`         |
| 7     | `feat/`                              | `feat/document-version-replacement`     |
| 8     | `feat/`                              | `feat/celery-document-ingestion`        |
| 9     | `feat/`                              | `feat/admin-analytics-routes`           |
| 10    | `feat/`                              | `feat/chat-streaming-ui`                |
| 11    | `feat/`, `chore/`                    | `feat/synthetic-document-generator`     |
| 12    | `feat/`, `test/`                     | `feat/ragas-evaluation-runner`          |
| 13    | `refactor/`                          | `refactor/di-container-audit`           |
| 14    | `feat/`, `perf/`, `security/`, `ci/` | `feat/structured-logging`               |

---

## Multi-Model Routing Strategy

### How It Works

```
User Query
    │
    ▼
┌──────────────┐
│ Query Router  │ ← scores complexity (0.0 - 1.0)
└──────┬───────┘
       │
       ├── score < 0.4 ──→ CHEAP model (Haiku / GPT-4o-mini / Groq Llama)
       │                    Examples: "What's my deductible?"
       │                             "Am I enrolled in dental?"
       │                             "What's the copay for ER visits?"
       │
       ├── score ≥ 0.4 ──→ POWERFUL model (Sonnet / GPT-4o / Opus)
       │                    Examples: "Compare health vs dental coverage for my family"
       │                             "Explain how my plan changes if I add a dependent"
       │                             "What are my out-of-pocket maximums across all plans?"
       │
       └── POWERFUL unavailable? ──→ fallback to CHEAP model (never crash)
```

### Complexity Scoring Signals
- Number of concepts/entities in the query
- Presence of comparison/reasoning keywords ("compare", "explain why", "recommend", "which is better")
- Query length and grammatical complexity
- Whether multiple policy types are referenced
- Whether personal enrollment data needs cross-referencing

### Configuration

```env
# .env — model tiers are config-driven
LLM_CHEAP_MODEL=claude-haiku-4-5-20251001
LLM_POWERFUL_MODEL=claude-sonnet-4-6
LLM_EMBEDDING_MODEL=text-embedding-3-small
LLM_COMPLEXITY_THRESHOLD=0.4
LLM_FALLBACK_ENABLED=true

# If POWERFUL_MODEL is empty or key is missing → all queries go to CHEAP_MODEL
# EMBEDDING_MODEL is separate — embeddings use a different (cheaper) model than generation.
# No code changes needed. Zero errors. Graceful degradation.
```

---

## RAG Quality Evaluation & Improvement Plan

### Automated Metrics (RAGAS Framework)

| Metric              | What It Measures                                      | Target |
| ------------------- | ----------------------------------------------------- | ------ |
| Faithfulness        | Is the answer grounded in retrieved context? (no hallucination) | > 0.85 |
| Answer Relevancy    | Does the answer actually address the question?        | > 0.80 |
| Context Precision   | Are the retrieved chunks relevant to the query?       | > 0.75 |
| Context Recall      | Did retrieval find all relevant chunks?               | > 0.70 |

### Golden Test Dataset
- Manually curated set of 100+ Q&A pairs across all employers and policy types.
- Covers: simple lookups, multi-policy comparisons, personal enrollment queries, edge cases, off-topic rejections.
- Stored in `data/eval/golden_dataset.json`.
- Run evaluation pipeline on every chunking/prompt/model change to catch regressions.

### User Feedback Loop
- Thumbs up/down buttons on every assistant response in the chat UI.
- Optional text feedback ("What was wrong?") on thumbs down.
- Feedback stored in PostgreSQL linked to the conversation, query, retrieved chunks, and model used.
- Weekly aggregation: which query types have low satisfaction? Which employers? Which policy types?

### Continuous Improvement Cycle
1. Run RAGAS eval → identify weak metric.
2. If context precision is low → tune chunking strategy (size, overlap, metadata filters).
3. If faithfulness is low → tighten system prompt, add "cite your sources" instructions.
4. If answer relevancy is low → improve query preprocessing or add reranking step.
5. If user feedback is negative on specific topics → add targeted golden Q&A pairs, fine-tune prompts.
6. Log every LLM call with: model used, tokens consumed, latency, chunks retrieved, user rating → enables data-driven optimization.

---

## Data Pipeline: How Documents Flow From Source to Query

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCUMENT INGESTION FLOW                       │
│                                                                 │
│  Source PDFs/DOCX/XLSX/XML                                      │
│       │                                                         │
│       ▼                                                         │
│  Upload API (or seed script)                                    │
│       │                                                         │
│       ▼                                                         │
│  Celery Task Triggered ─────────────────────────────────┐       │
│       │                                                 │       │
│       ▼                                                 │       │
│  File Type Detection                                    │       │
│       │                                                 │       │
│       ▼                                                 │       │
│  ProcessorFactory → routes to correct processor         │       │
│       │  (PDFProcessor / DOCXProcessor / etc.)          │       │
│       │                                                 │       │
│       ▼                                                 │       │
│  Raw Text + Structure Extracted                         │       │
│       │                                                 │       │
│       ▼                                                 │       │
│  Metadata Extractor (headings, sections, page nums)     │       │
│       │                                                 │       │
│       ▼                                                 │       │
│  Semantic Chunker (split by meaning, ~400-600 tokens)   │       │
│       │                                                 │       │
│       ▼                                                 │       │
│  Embedding Generation (via LLMPort.embed())             │       │
│       │                                                 │       │
│       ├──→ Pinecone: vectors + metadata                 │       │
│       │    (namespaced by employer_id)                   │       │
│       │                                                 │       │
│       ├──→ PostgreSQL: chunk references, doc status     │       │
│       │    (who owns it, processing state)              │       │
│       │                                                 │       │
│       └──→ EventBus: DocumentProcessedEvent             │       │
│            (notifies frontend via SSE)                  │       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      QUERY FLOW                                 │
│                                                                 │
│  User asks: "What's my dental deductible?"                      │
│       │                                                         │
│       ▼                                                         │
│  Guardrails Check ── off-topic? → reject immediately            │
│       │                                                         │
│       ▼                                                         │
│  Redis Cache Check ── identical recent query? → return cached   │
│       │                                                         │
│       ▼                                                         │
│  Query Router ── score complexity → pick model tier             │
│       │                                                         │
│       ▼                                                         │
│  Embed Query (via LLMPort.embed())                              │
│       │                                                         │
│       ▼                                                         │
│  Pinecone Search (filtered: employer_id + policy_type)          │
│       │                                                         │
│       ▼                                                         │
│  Fetch User Enrollment Data (PostgreSQL)                        │
│       │                                                         │
│       ▼                                                         │
│  Assemble Prompt (system prompt + chunks + enrollment + history)│
│       │                                                         │
│       ▼                                                         │
│  LLM Generate Stream (via selected model tier)                  │
│       │                                                         │
│       ▼                                                         │
│  SSE → React Frontend (tokens appear in real-time)              │
│       │                                                         │
│       ▼                                                         │
│  Cache Response in Redis + Save to PostgreSQL                   │
│       │                                                         │
│       ▼                                                         │
│  Analytics Logging:                                             │
│    ├── LLMCostLog (model, tokens, cost, employer_id)            │
│    ├── RequestLatencyLog (total, retrieval, llm latency)        │
│    ├── Low confidence? → FlaggedResponse (for admin review)     │
│    └── Topic classification → TopicLog (for heatmap)            │
└─────────────────────────────────────────────────────────────────┘
```

### Data Source Acquisition

**Real Government PDFs (one-time download script)**
- `scripts/download_gov_docs.py` fetches from public URLs:
  - healthcare.gov → Summary of Benefits and Coverage (SBC) templates
  - OPM.gov → Federal employee health plan brochures
  - DOL.gov → ERISA compliance summaries
  - CMS.gov → Medicare/Medicaid plan summaries
- Saved to `data/gov_pdfs/` organized by source.
- Target: 50-100 real documents.

**Synthetic Employer Policy Docs (LLM-generated)**
- `scripts/generate_synthetic_docs.py` calls LiteLLM to produce:
  - Health, dental, vision plan summaries for 5 fictional employers
  - Employee handbooks (benefits sections)
  - Open enrollment guides and FAQ documents
- Converted to PDF/DOCX files saved in `data/synthetic/`.
- Target: 50+ documents across 5 employers.

**Seed Script**
- `scripts/seed_data.py` creates:
  - 5 employers with realistic company names
  - 10-20 employees per employer with randomized enrollments
  - Policies (health, dental, vision, life, disability) per employer
  - Triggers Celery ingestion for all seeded documents

---

## Folder Structure

```
policypal/
├── .gitignore                           # Secrets, venvs, node_modules, generated data
├── .gitattributes                       # Line endings + binary/lfs handling
├── .pre-commit-config.yaml              # Local gates: ruff, mypy, eslint, commitlint, gitleaks
├── commitlint.config.js                 # Conventional Commits enforcement
├── CHANGELOG.md                         # Generated from Conventional Commit history
├── CONTRIBUTING.md                      # Branching, commit, and PR rules for humans and agents
│
├── .github/
│   ├── CODEOWNERS                       # Required reviewers per path (auth, tenancy, migrations)
│   ├── pull_request_template.md         # Default template
│   ├── PULL_REQUEST_TEMPLATE/
│   │   ├── feature.md                   # feat/ branches
│   │   ├── bugfix.md                    # fix/ and hotfix/ branches
│   │   ├── refactor.md                  # refactor/ and perf/ branches
│   │   ├── chore.md                     # chore/, build/, ci/ branches
│   │   ├── security.md                  # security/ branches
│   │   └── docs.md                      # docs/ branches
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   └── config.yml
│   ├── labeler.yml                      # Auto-labels PRs by branch prefix and changed paths
│   └── workflows/
│       ├── ci.yml                       # Lint, typecheck, test, build on every PR
│       ├── docker-build.yml             # Backend + frontend image build validation
│       ├── migration-check.yml          # Alembic applies cleanly, no model drift
│       ├── secret-scan.yml              # gitleaks on the PR diff
│       ├── dependency-audit.yml         # pip-audit + npm audit
│       ├── rag-eval.yml                 # RAGAS regression gate on retrieval/prompt changes
│       ├── pr-lint.yml                  # Conventional Commit PR title + branch name check
│       └── release.yml                  # Tag, changelog, and version bump on main
│
├── docker-compose.yml
├── docker-compose.override.yml          # Local dev overrides (hot reload, debug ports)
├── .env.example
├── Makefile
├── README.md                            # Auto-updated with every code change
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/
│   │   └── versions/
│   │
│   ├── src/
│   │   ├── main.py                          # FastAPI app factory
│   │   ├── config.py                        # Pydantic Settings (env-driven)
│   │   │
│   │   ├── core/                            # === DOMAIN CORE (no framework imports) ===
│   │   │   ├── ports/                       # Abstract interfaces (ABCs)
│   │   │   │   ├── llm_port.py              # LLM abstraction
│   │   │   │   ├── vector_store_port.py     # Vector DB abstraction
│   │   │   │   ├── event_bus_port.py        # Event bus abstraction (Kafka-ready)
│   │   │   │   ├── cache_port.py            # Cache abstraction
│   │   │   │   ├── document_processor_port.py
│   │   │   │   └── repository_ports.py      # All repo interfaces
│   │   │   │
│   │   │   ├── domain/                      # Pure domain models (dataclasses/Pydantic)
│   │   │   │   ├── employer.py
│   │   │   │   ├── employee.py
│   │   │   │   ├── policy.py
│   │   │   │   ├── document.py
│   │   │   │   ├── conversation.py
│   │   │   │   ├── feedback.py              # User feedback (thumbs up/down)
│   │   │   │   ├── analytics.py             # LLM cost log, latency record, flagged response, guardrail rejection
│   │   │   │   └── events.py                # Domain event definitions
│   │   │   │
│   │   │   └── services/                    # Business logic (depends only on ports)
│   │   │       ├── rag_service.py           # Retrieval + generation orchestration
│   │   │       ├── query_router.py          # Multi-model complexity routing
│   │   │       ├── guardrails_service.py    # Domain restriction + off-topic rejection
│   │   │       ├── document_service.py      # Ingestion orchestration
│   │   │       ├── auth_service.py
│   │   │       ├── policy_service.py
│   │   │       ├── employer_service.py
│   │   │       ├── conversation_service.py
│   │   │       ├── feedback_service.py      # User feedback collection + aggregation
│   │   │       └── analytics_service.py     # Aggregation logic for admin dashboard
│   │   │
│   │   ├── adapters/                        # === INFRASTRUCTURE ADAPTERS ===
│   │   │   ├── llm/
│   │   │   │   ├── litellm_adapter.py       # LiteLLM implementation
│   │   │   │   └── mock_llm_adapter.py      # For dev/testing
│   │   │   │
│   │   │   ├── vector_store/
│   │   │   │   └── pinecone_adapter.py
│   │   │   │
│   │   │   ├── cache/
│   │   │   │   ├── redis_cache_adapter.py   # Production cache
│   │   │   │   └── in_memory_cache.py       # Dev fallback
│   │   │   │
│   │   │   ├── event_bus/
│   │   │   │   ├── in_memory_event_bus.py   # Current: sync in-memory
│   │   │   │   └── kafka_event_bus.py       # Future: drop-in Kafka adapter
│   │   │   │
│   │   │   ├── document_processors/
│   │   │   │   ├── processor_factory.py     # Routes file type → processor
│   │   │   │   ├── pdf_processor.py
│   │   │   │   ├── docx_processor.py
│   │   │   │   ├── xlsx_processor.py
│   │   │   │   └── xml_processor.py
│   │   │   │
│   │   │   ├── persistence/                 # SQLAlchemy repos
│   │   │   │   ├── models.py                # ORM models
│   │   │   │   ├── database.py              # Engine, session factory
│   │   │   │   ├── employer_repo.py
│   │   │   │   ├── employee_repo.py
│   │   │   │   ├── policy_repo.py
│   │   │   │   ├── document_repo.py
│   │   │   │   ├── conversation_repo.py
│   │   │   │   ├── feedback_repo.py
│   │   │   │   └── analytics_repo.py        # Cost logs, latency, flags, rejections
│   │   │   │
│   │   │   └── chunking/
│   │   │       ├── chunker_pipeline.py      # Orchestrates chunking stages
│   │   │       ├── semantic_chunker.py
│   │   │       └── metadata_extractor.py
│   │   │
│   │   ├── api/                             # === FASTAPI LAYER ===
│   │   │   ├── dependencies.py              # DI: wires ports → adapters
│   │   │   ├── middleware/
│   │   │   │   ├── auth_middleware.py
│   │   │   │   ├── rate_limiter.py
│   │   │   │   ├── retry_middleware.py       # Exponential backoff for LLM/Pinecone
│   │   │   │   ├── request_logger.py        # Logs every request for latency tracking
│   │   │   │   └── tenant_context.py        # Sets employer context per request
│   │   │   │
│   │   │   └── routes/
│   │   │       ├── auth_routes.py
│   │   │       ├── chat_routes.py           # SSE streaming endpoint
│   │   │       ├── document_routes.py
│   │   │       ├── employer_routes.py
│   │   │       ├── employee_routes.py
│   │   │       ├── policy_routes.py
│   │   │       ├── feedback_routes.py
│   │   │       ├── health_routes.py         # /health and /ready probes
│   │   │       └── admin_routes.py          # Admin-only analytics & observability APIs
│   │   │
│   │   └── workers/                         # === CELERY TASKS ===
│   │       ├── celery_app.py
│   │       ├── document_ingestion_task.py
│   │       └── embedding_task.py
│   │
│   └── scripts/
│       ├── seed_data.py                     # Seed employers, employees, policies
│       ├── generate_synthetic_docs.py       # LLM-generated policy documents
│       └── download_gov_docs.py             # Fetch real government PDFs
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   │
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       │
│       ├── api/                             # API client layer
│       │   ├── client.ts                    # Axios instance + interceptors
│       │   ├── auth.ts
│       │   ├── chat.ts                      # SSE handling
│       │   ├── documents.ts
│       │   ├── employers.ts
│       │   └── admin.ts                     # Admin analytics API calls
│       │
│       ├── stores/                          # Zustand state management
│       │   ├── authStore.ts
│       │   ├── chatStore.ts
│       │   ├── employerStore.ts
│       │   └── adminStore.ts               # Admin dashboard state
│       │
│       ├── components/
│       │   ├── common/                      # Shared UI components
│       │   ├── chat/                        # Chat interface components
│       │   │   ├── ChatWindow.tsx
│       │   │   ├── MessageBubble.tsx
│       │   │   ├── StreamingMessage.tsx
│       │   │   ├── ChatInput.tsx
│       │   │   └── FeedbackButtons.tsx      # Thumbs up/down per message
│       │   │
│       │   ├── admin/                       # Admin dashboard components
│       │   │   ├── DocumentUpload.tsx
│       │   │   ├── EmployerManagement.tsx
│       │   │   ├── AnalyticsDashboard.tsx
│       │   │   ├── CostDashboard.tsx        # LLM spend tracking
│       │   │   ├── LatencyMonitor.tsx        # P50/P95/P99 charts
│       │   │   ├── FlaggedResponses.tsx      # Low-confidence response review
│       │   │   ├── GuardrailsLog.tsx         # Rejected queries review
│       │   │   ├── UnansweredQueries.tsx     # Queries with no good answer
│       │   │   ├── TopicHeatmap.tsx          # Which policy areas get most questions
│       │   │   └── DocumentHealth.tsx        # Stale/failed doc pipeline status
│       │   │
│       │   └── employer/                    # Employer portal components
│       │       ├── SelfServeUpload.tsx
│       │       ├── UserManagement.tsx
│       │       └── PolicyOverview.tsx
│       │
│       ├── pages/
│       │   ├── LoginPage.tsx
│       │   ├── ChatPage.tsx
│       │   ├── AdminDashboard.tsx
│       │   └── EmployerPortal.tsx
│       │
│       └── hooks/
│           ├── useSSE.ts                    # SSE streaming hook
│           ├── useAuth.ts
│           └── useDocumentUpload.ts
│
├── data/
│   ├── gov_pdfs/                            # Downloaded real government PDFs
│   ├── synthetic/                           # Generated synthetic policy docs
│   └── eval/
│       └── golden_dataset.json              # Curated Q&A pairs for RAG evaluation
│
└── eval/
    ├── run_eval.py                          # RAGAS evaluation runner
    ├── eval_config.yaml                     # Metrics, thresholds, dataset paths
    └── reports/                             # Generated evaluation reports
```

---

## Implementation Steps

> Every step below is delivered on its own branch and merged through its own pull request, following the Per-Step Delivery Loop defined above. Nothing is committed directly to `main`.

### Phase 0 — Git Repository & Delivery Workflow

**Step 0.1 — Initialize the repository and trunk**
> Branch: `chore/repo-initialization` → PR type: Chore
- Run `git init`, create the initial commit on `main`, and connect the remote origin.
- Write `.gitignore` covering `.env`, `.venv/`, `__pycache__/`, `node_modules/`, `dist/`, `*.pyc`, `data/gov_pdfs/`, `data/synthetic/`, `eval/reports/`, and IDE folders.
- Write `.gitattributes` to normalize line endings (`* text=auto`) and mark PDF/DOCX/XLSX as binary.
- Push `main` to origin and set it as the default branch.

**Step 0.2 — Branch protection and ownership**
> Branch: `chore/branch-protection-and-codeowners` → PR type: Chore
- Protect `main`: block direct pushes, require a PR, require one approval, require linear history, require signed commits, require conversation resolution, and require branches to be up to date before merge.
- Add `.github/CODEOWNERS` requiring two approvals on `backend/src/core/services/auth_service.py`, `api/middleware/tenant_context.py`, `adapters/persistence/`, and `alembic/versions/`.
- Enable automatic branch deletion on merge and restrict the merge strategy to squash-only.

**Step 0.3 — Commit, branch, and PR conventions**
> Branch: `chore/commit-and-pr-conventions` → PR type: Chore
- Add `commitlint.config.js` enforcing Conventional Commits with the scope list defined in the Git Workflow section.
- Add `.pre-commit-config.yaml` wiring ruff, mypy, eslint, prettier, commitlint, and gitleaks.
- Add the default PR template plus the per-type templates in `.github/PULL_REQUEST_TEMPLATE/` (feature, bugfix, refactor, chore, security, docs).
- Add issue templates for bug reports and feature requests.
- Add `.github/labeler.yml` so PRs are auto-labeled by branch prefix (`type: feature`, `type: bug`, and so on) and by changed path.
- Add `CONTRIBUTING.md` documenting the branching model, naming rules, commit format, PR expectations, and merge policy.

**Step 0.4 — Continuous integration pipelines**
> Branch: `ci/core-pipelines` → PR type: CI
- Add `.github/workflows/ci.yml` running backend lint, format check, `mypy --strict`, `pytest`, plus frontend lint, `tsc --noEmit`, and build.
- Add `pr-lint.yml` validating the PR title and branch name against the Conventional Commits and branch-naming rules.
- Add `secret-scan.yml` (gitleaks) and `dependency-audit.yml` (pip-audit, npm audit).
- Add `docker-build.yml` and `migration-check.yml` (Alembic applies cleanly against a PostgreSQL service container).
- Add `release.yml` that derives the semantic version from merged commit types, generates `CHANGELOG.md`, and creates a signed tag on `main`.
- Mark every job as a required status check on `main`.

---

### Phase 1 — Project Scaffolding & Infrastructure

**Step 1.1 — Initialize project skeleton**
> Branch: `chore/project-skeleton` → PR type: Chore
- Create the full folder structure shown above (empty `__init__.py` files, placeholder modules).
- Set up `pyproject.toml` with all backend dependencies.
- Set up `package.json` with React + TypeScript + Tailwind.
- Create `.env.example` with all required environment variables.
- Create `Makefile` with common commands (`make dev`, `make build`, `make migrate`, etc.).
- Create initial `README.md` with project overview, setup steps, and architecture summary.

**Step 1.2 — Docker Compose setup**
> Branch: `build/docker-compose-services` → PR type: Chore
- Write `docker-compose.yml` with services: `backend`, `frontend`, `postgres`, `redis`, `celery-worker`.
- Configure volumes, networks, and health checks.
- Add a `docker-compose.override.yml` for local dev (hot reload, debug ports).
- Verify all containers start cleanly with `docker compose up`.
- Update README.md with Docker setup instructions.

**Step 1.3 — PostgreSQL + Alembic setup**
> Branch: `feat/postgres-schema-and-migrations` → PR type: Feature (requires two approvals per CODEOWNERS)
- Define SQLAlchemy async engine and session factory in `adapters/persistence/database.py`.
- Write ORM models for: `Employer`, `Employee`, `Policy`, `EmployeePolicy` (enrollment), `Document`, `DocumentChunk`, `Conversation`, `Message`, `Feedback`, `LLMCostLog`, `RequestLatencyLog`, `FlaggedResponse`, `GuardrailRejection`.
- Initialize Alembic and generate the first migration.
- Run migration inside Docker to verify schema creation.
- Update README.md with database schema overview.

**Step 1.4 — Configuration management**
> Branch: `feat/typed-configuration` → PR type: Feature
- Build `config.py` using Pydantic `BaseSettings` with environment variable loading.
- Define separate config sections: `DatabaseConfig`, `RedisConfig`, `PineconeConfig`, `LLMConfig`, `AuthConfig`, `CacheConfig`.
- Ensure every secret comes from env vars, never hardcoded.

**Step 1.5 — Health check endpoints**
> Branch: `feat/health-and-readiness-probes` → PR type: Feature
- `GET /health` — returns 200 if the server is running (liveness probe).
- `GET /ready` — checks PostgreSQL, Redis, and Pinecone connectivity (readiness probe).
- Used by Docker Compose health checks and any future orchestrator.

---

### Phase 2 — Core Domain & Ports

**Step 2.1 — Domain models**
> Branch: `feat/core-domain-models` → PR type: Feature
- Define pure domain models as Pydantic `BaseModel` or `dataclass` in `core/domain/`.
- Models: `Employer`, `Employee`, `Policy`, `Enrollment`, `Document`, `DocumentChunk`, `Conversation`, `Message`, `Feedback`.
- Analytics models (in `core/domain/analytics.py`): `LLMCostLog`, `RequestLatencyLog`, `FlaggedResponse`, `GuardrailRejection`.
- These must have zero imports from FastAPI, SQLAlchemy, or any adapter.

**Step 2.2 — Port interfaces (ABCs)**
> Branch: `feat/core-port-interfaces` → PR type: Feature
- Define all abstract base classes in `core/ports/`:
  - `LLMPort`: `generate()`, `generate_stream()`, `embed()`
  - `VectorStorePort`: `upsert()`, `query()`, `delete_by_metadata()`
  - `EventBusPort`: `publish()`, `subscribe()`, `unsubscribe()`
  - `CachePort`: `get()`, `set()`, `delete()`, `exists()`
  - `DocumentProcessorPort`: `extract_text()`, `extract_metadata()`
  - Repository ports: one ABC per entity with CRUD + custom query methods (including `AnalyticsRepository` for cost logs, latency logs, flagged responses, guardrail rejections).

**Step 2.3 — Domain events**
> Branch: `feat/domain-events` → PR type: Feature
- Define event classes in `core/domain/events.py`:
  - `DocumentUploadedEvent`, `DocumentProcessedEvent`, `DocumentEmbeddedEvent`
  - `DocumentVersionReplacedEvent` (old vectors purged, new ones indexed)
  - `EmployerCreatedEvent`, `EmployeeEnrolledEvent`
  - `ChatMessageReceivedEvent`, `ChatResponseGeneratedEvent`
  - `FeedbackReceivedEvent`
  - `LowConfidenceResponseEvent` (auto-flagged for admin review)
  - `GuardrailRejectionEvent` (query blocked, logged for admin tuning)
- Each event is a frozen dataclass with a `timestamp`, `event_type`, and payload.

---

### Phase 3 — Infrastructure Adapters

**Step 3.1 — In-memory event bus adapter**
> Branch: `feat/in-memory-event-bus` → PR type: Feature
- Implement `InMemoryEventBus` that fulfills `EventBusPort`.
- Uses a dictionary of `{event_type: [list of handler callables]}`.
- Supports sync and async handlers.
- Write a docstring explaining: "Swap this for `KafkaEventBus` by implementing the same port."

**Step 3.2 — LiteLLM adapter**
> Branch: `feat/litellm-adapter` → PR type: Feature
- Implement `LiteLLMAdapter` that fulfills `LLMPort`.
- `generate()` calls `litellm.completion()` with configurable `model` param.
- `generate_stream()` calls `litellm.completion(stream=True)` and yields chunks.
- `embed()` calls `litellm.embedding()`.
- Model name comes from config — change the env var, change the model.
- Build a `MockLLMAdapter` that returns canned responses for dev/testing.
- Integrate retry with exponential backoff (tenacity library) on all LLM calls.

**Step 3.3 — Pinecone adapter**
> Branch: `feat/pinecone-vector-store-adapter` → PR type: Feature
- Implement `PineconeAdapter` that fulfills `VectorStorePort`.
- `upsert()` takes chunks with embeddings + metadata (employer_id, policy_id, doc_id, chunk_index, doc_version).
- `query()` takes an embedding + metadata filter (always scoped to employer_id at minimum).
- `delete_by_metadata()` for document versioning (purge old vectors when re-uploading).
- Namespace strategy: one Pinecone namespace per employer for hard tenant isolation.
- Retry with exponential backoff on all Pinecone calls.

**Step 3.4 — Redis cache adapter**
> Branch: `feat/redis-cache-adapter` → PR type: Feature
- Implement `RedisCacheAdapter` that fulfills `CachePort`.
- Cache key = hash of (employer_id + query_text + model_tier).
- TTL configurable per query type (default 1 hour).
- `InMemoryCacheAdapter` for dev/testing without Redis.

**Step 3.5 — PostgreSQL repository adapters**
> Branch: `feat/postgres-repository-adapters` → PR type: Feature (requires two approvals per CODEOWNERS)
- Implement all repository interfaces using SQLAlchemy async sessions.
- Each repo method maps domain models ↔ ORM models (never leak ORM models out).
- Use the Unit of Work pattern: a single session per request, committed at the API layer.

**Step 3.6 — Document processor adapters**
> Branch: `feat/document-processor-adapters` → PR type: Feature
- Implement `PDFProcessor` (PyMuPDF + unstructured for layout-aware extraction).
- Implement `DOCXProcessor` (python-docx for text + table extraction).
- Implement `XLSXProcessor` (openpyxl for cell-level extraction with sheet awareness).
- Implement `XMLProcessor` (lxml for structured field extraction).
- Build `ProcessorFactory`: given a file extension, returns the correct processor instance.

---

### Phase 4 — Chunking & Embedding Pipeline

**Step 4.1 — Metadata-aware chunker**
> Branch: `feat/metadata-extractor` → PR type: Feature
- Build `MetadataExtractor` that parses document structure: headings, sections, tables, page numbers.
- Each chunk carries metadata: `section_title`, `page_number`, `document_title`, `policy_type`, `employer_id`.

**Step 4.2 — Semantic chunker**
> Branch: `feat/semantic-chunker` → PR type: Feature (triggers the `rag-eval` CI gate)
- Build `SemanticChunker` that splits text by semantic boundaries (sentence-level similarity).
- Uses embeddings to detect topic shifts — avoids splitting mid-concept.
- Configurable chunk size (target ~400-600 tokens) and overlap.

**Step 4.3 — Chunking pipeline orchestration**
> Branch: `feat/chunker-pipeline` → PR type: Feature (triggers the `rag-eval` CI gate)
- Build `ChunkerPipeline` that chains: raw text → metadata extraction → semantic splitting → chunk enrichment.
- Output: list of `DocumentChunk` domain objects with text + metadata + position info.

**Step 4.4 — Embedding and indexing**
> Branch: `feat/embedding-and-indexing-task` → PR type: Feature
- Celery task: takes processed chunks → generates embeddings via `LLMPort.embed()` → upserts to Pinecone via `VectorStorePort.upsert()`.
- Stores chunk references in PostgreSQL (`DocumentChunk` table) for traceability.
- Publishes `DocumentEmbeddedEvent` on completion.

---

### Phase 5 — Authentication & Multi-Tenancy

**Step 5.1 — Auth service + JWT**
> Branch: `feat/auth-service-jwt` → PR type: Security (requires two approvals per CODEOWNERS)
- Implement OAuth2 password flow with JWT tokens (access + refresh).
- Tokens carry: `user_id`, `employer_id`, `role` (admin / employer / employee).
- Use `python-jose` for JWT, `passlib[bcrypt]` for password hashing.

**Step 5.2 — Auth middleware**
> Branch: `security/auth-middleware-role-guards` → PR type: Security (requires two approvals per CODEOWNERS)
- FastAPI dependency that decodes JWT, validates expiry, and attaches `CurrentUser` to the request.
- Role-based guards: `require_role("admin")`, `require_role("employer")`, etc.

**Step 5.3 — Tenant context middleware**
> Branch: `security/tenant-context-isolation` → PR type: Security (requires two approvals per CODEOWNERS)
- Extracts `employer_id` from the JWT on every request.
- Injects it into a context variable (Python `contextvars`).
- Every repository query and every vector search automatically scopes to this employer_id.
- An employee can never see another employer's data. Period.

---

### Phase 6 — RAG Pipeline (Core Feature)

**Step 6.1 — Guardrails service**
> Branch: `feat/guardrails-service` → PR type: Feature (triggers the `rag-eval` CI gate)
- Build a lightweight classifier that determines if a query is policy-related.
- Uses keyword matching + a small LLM call (cheap model) for ambiguous cases.
- Off-topic queries get a polite rejection BEFORE any retrieval or expensive LLM call happens.
- Configurable allowed domains: health, dental, vision, life, disability, enrollment, coverage, claims.
- This saves cost (no Pinecone search, no LLM generation for irrelevant queries).
- Every rejection is logged as a `GuardrailRejection` record (query text, rejection reason, employer_id, timestamp) and published as `GuardrailRejectionEvent` for admin review.

**Step 6.2 — Query router (multi-model)**
> Branch: `feat/query-complexity-router` → PR type: Feature (triggers the `rag-eval` CI gate)
- Build `QueryRouter` that scores query complexity on a 0.0–1.0 scale.
- Signals: entity count, comparison keywords, query length, multi-policy references.
- Routes to cheap or powerful model tier based on configurable threshold.
- Fallback logic: if powerful model is not configured or returns an error, automatically routes to cheap model.
- All routing decisions are logged for later analysis.

**Step 6.3 — Retrieval**
> Branch: `feat/rag-retrieval` → PR type: Feature (triggers the `rag-eval` CI gate)
- Embed the user's query via `LLMPort.embed()`.
- Check Redis cache first — if identical query was answered recently, return cached response.
- Search Pinecone via `VectorStorePort.query()` with metadata filters:
  - Always: `employer_id = current_user.employer_id`
  - If policy type detected: `policy_type = detected_type`
- Retrieve top-k chunks (configurable, default k=5).
- Fetch the user's enrollment data from PostgreSQL if the question is personal.

**Step 6.4 — Context assembly + prompt engineering**
> Branch: `feat/prompt-assembly` → PR type: Feature (triggers the `rag-eval` CI gate)
- Build the system prompt with:
  - Role definition (benefits assistant, scoped to this employer).
  - Domain restriction instructions (reject off-topic, never hallucinate, cite sources).
  - Retrieved chunks as context (with source attribution metadata).
  - User's enrollment info if relevant.
- Use a `PromptTemplate` class with named slots — easy to iterate on prompts without touching logic.

**Step 6.5 — Streaming generation + analytics logging**
> Branch: `feat/rag-streaming-generation` → PR type: Feature (triggers the `rag-eval` CI gate)
- Call `LLMPort.generate_stream()` with the assembled prompt using the router-selected model.
- Yield tokens as they arrive.
- Append source citations at the end (which documents/sections were used).
- Cache the complete response in Redis after streaming finishes.
- Log to `LLMCostLog`: model used, input tokens, output tokens, estimated cost, employer_id, timestamp.
- Log to `RequestLatencyLog`: total request duration, retrieval latency, LLM latency, model tier.
- If retrieval confidence scores are below threshold → auto-flag as `FlaggedResponse` and publish `LowConfidenceResponseEvent`.

**Step 6.6 — Conversation memory**
> Branch: `feat/conversation-memory` → PR type: Feature
- Store each message pair (user query + assistant response) in PostgreSQL via `ConversationRepository`.
- On each new query, load the last N messages from the current conversation as context.
- Conversations are scoped per user and isolated per employer.

---

### Phase 7 — Document Versioning

**Step 7.1 — Version tracking**
> Branch: `feat/document-version-tracking` → PR type: Feature (requires two approvals per CODEOWNERS)
- Each document has a `version` field in PostgreSQL (integer, starts at 1).
- Uploading a document with the same name under the same employer increments the version.

**Step 7.2 — Vector replacement**
> Branch: `feat/document-version-replacement` → PR type: Feature
- On re-upload: Celery task first calls `VectorStorePort.delete_by_metadata(doc_id=old_doc_id)` to purge old vectors.
- Then processes and indexes the new document normally.
- Old chunk references in PostgreSQL are soft-deleted (marked inactive, not destroyed).
- Publishes `DocumentVersionReplacedEvent`.

**Step 7.3 — Cache invalidation**
> Branch: `feat/version-cache-invalidation` → PR type: Feature
- On document version change, invalidate all cached queries for that employer + policy type.
- Prevents stale answers from old document versions.

---

### Phase 8 — Celery Workers & Document Ingestion

**Step 8.1 — Celery + Redis setup**
> Branch: `feat/celery-app-configuration` → PR type: Feature
- Configure Celery app in `workers/celery_app.py` with Redis as broker and result backend.
- Set up task routing, retries, and dead-letter handling.

**Step 8.2 — Document ingestion task**
> Branch: `feat/celery-document-ingestion` → PR type: Feature
- Celery task triggered when a document is uploaded:
  1. Detect file type → get processor from factory.
  2. Extract text and structure.
  3. Run chunking pipeline.
  4. Generate embeddings.
  5. Upsert to Pinecone.
  6. Update document status in PostgreSQL (processing → ready / failed).
  7. Publish `DocumentProcessedEvent`.

**Step 8.3 — Ingestion status tracking**
> Branch: `feat/ingestion-status-tracking` → PR type: Feature
- API endpoint to check document processing status.
- SSE push to frontend when processing completes.

---

### Phase 9 — API Routes

**Step 9.1 — Auth routes**
> Branch: `feat/auth-routes` → PR type: Feature (requires two approvals per CODEOWNERS)
- `POST /api/auth/register` — register new user (employer or employee).
- `POST /api/auth/login` — issue JWT tokens.
- `POST /api/auth/refresh` — refresh access token.
- `GET /api/auth/me` — current user profile.

**Step 9.2 — Chat routes**
> Branch: `feat/chat-sse-routes` → PR type: Feature
- `POST /api/chat/conversations` — create a new conversation.
- `GET /api/chat/conversations` — list user's conversations.
- `POST /api/chat/conversations/{id}/messages` — send a message (returns SSE stream).
- `GET /api/chat/conversations/{id}/messages` — get conversation history.

**Step 9.3 — Document routes**
> Branch: `feat/document-routes` → PR type: Feature
- `POST /api/documents/upload` — upload a document (employer/admin only).
- `GET /api/documents` — list documents for current employer.
- `GET /api/documents/{id}/status` — check processing status.
- `DELETE /api/documents/{id}` — remove document and its vectors.

**Step 9.4 — Employer & employee management routes**
> Branch: `feat/employer-and-employee-routes` → PR type: Feature
- CRUD for employers (admin only).
- CRUD for employees under an employer.
- Policy assignment: enroll/unenroll employees from policies.
- `GET /api/employees/me/policies` — employee sees their own enrolled policies.

**Step 9.5 — Feedback routes**
> Branch: `feat/feedback-routes` → PR type: Feature
- `POST /api/feedback` — submit thumbs up/down + optional text for a message.
- `GET /api/feedback/analytics` — aggregated feedback stats (admin only).

**Step 9.6 — Admin analytics routes (admin role only)**
> Branch: `feat/admin-analytics-routes` → PR type: Feature
- `GET /api/admin/cost-dashboard` — LLM spend: total, per model, per employer, per day. Filterable by date range.
- `GET /api/admin/cost-dashboard/alerts` — days where spend exceeded configured threshold.
- `GET /api/admin/latency` — P50, P95, P99 response times. Broken down by model tier and time window.
- `GET /api/admin/flagged-responses` — list of auto-flagged low-confidence responses with full conversation context.
- `PATCH /api/admin/flagged-responses/{id}` — mark as reviewed / dismiss / escalate.
- `GET /api/admin/guardrail-rejections` — list of blocked queries with rejection reasons. Filterable by date, employer.
- `GET /api/admin/unanswered-queries` — queries where the bot responded with "I don't have enough information."
- `GET /api/admin/topic-heatmap` — query volume aggregated by policy type (health, dental, vision, etc.) over time.
- `GET /api/admin/document-health` — documents with status: failed ingestion, stale (not updated in 6+ months), zero query hits.
- `GET /api/admin/overview` — top-level summary: total queries today/week/month, active users, document count, avg satisfaction, cost this month.

**Step 9.7 — Health routes**
> Branch: `feat/health-routes` → PR type: Feature
- `GET /health` — liveness probe.
- `GET /ready` — readiness probe (checks DB, Redis, Pinecone).

---

### Phase 10 — React Frontend

**Step 10.1 — Project setup + routing**
> Branch: `chore/frontend-scaffold-and-routing` → PR type: Chore
- Initialize React 18 + TypeScript + Vite.
- Install and configure Tailwind CSS.
- Set up React Router with protected routes (role-based).
- Set up Zustand stores for auth, chat, and employer state.

**Step 10.2 — Auth pages**
> Branch: `feat/login-and-role-routing-ui` → PR type: Feature
- Login page with role selection (employee/employer/admin).
- JWT storage in memory (not localStorage — use httpOnly cookies or in-memory with refresh).
- Auto-redirect based on role after login.

**Step 10.3 — Chat interface**
> Branch: `feat/chat-streaming-ui` → PR type: Feature (screenshots required in the PR)
- `ChatWindow` with message history.
- `StreamingMessage` component that renders tokens as they arrive from SSE.
- `ChatInput` with send button and enter-to-send.
- Conversation sidebar: list, create new, switch between conversations.
- Source citations displayed below each assistant message (collapsible).
- `FeedbackButtons` (thumbs up/down) on every assistant message.

**Step 10.4 — Admin dashboard: management**
> Branch: `feat/admin-management-ui` → PR type: Feature (screenshots required in the PR)
- Document upload with drag-and-drop + progress indicator.
- Document list with processing status badges (processing / ready / failed) and version numbers.
- Employer management: create, edit, deactivate employers.

**Step 10.5 — Admin dashboard: overview & cost**
> Branch: `feat/admin-cost-dashboard-ui` → PR type: Feature (screenshots required in the PR)
- `AnalyticsDashboard` — top-level summary cards: total queries (today/week/month), active users, documents indexed, average satisfaction score, total LLM cost this month.
- `CostDashboard` — line chart of daily LLM spend. Breakdown table by model tier (cheap vs powerful). Breakdown by employer. Highlight days exceeding cost threshold in red. Date range picker.

**Step 10.6 — Admin dashboard: quality monitoring**
> Branch: `feat/admin-quality-monitoring-ui` → PR type: Feature (screenshots required in the PR)
- `FlaggedResponses` — table of auto-flagged low-confidence responses. Each row expandable to show: the user query, retrieved chunks (with similarity scores), the generated response, and the model used. Admin can mark as "reviewed", "false positive", or "needs document update".
- `GuardrailsLog` — table of rejected queries. Shows the query, rejection reason, employer, timestamp. Admin can identify false positives (legitimate queries wrongly blocked) and tune the guardrails configuration.
- `UnansweredQueries` — queries where the bot couldn't find enough context. Grouped by employer and policy type. Reveals document corpus gaps ("Employer X has zero dental policy docs — that's why all dental queries fail").

**Step 10.7 — Admin dashboard: operational health**
> Branch: `feat/admin-operational-health-ui` → PR type: Feature (screenshots required in the PR)
- `LatencyMonitor` — real-time-ish (polling) chart showing P50, P95, P99 response latencies. Separate lines for retrieval latency vs LLM generation latency. Filterable by model tier and time window (last hour, last 24h, last 7d).
- `DocumentHealth` — table of documents with issues: failed ingestion (with error message), stale documents (uploaded 6+ months ago, flagged for review), documents with zero query hits (possibly irrelevant or poorly chunked).
- `TopicHeatmap` — visual grid: rows = policy types (health, dental, vision, life, disability), columns = time buckets (weeks/months). Cell color intensity = query volume. Shows which topics are hot and trending.

**Step 10.8 — Employer portal**
> Branch: `feat/employer-portal-ui` → PR type: Feature (screenshots required in the PR)
- Self-serve document upload (scoped to their own employer).
- Employee management: invite, view, deactivate employees under their org.
- Policy overview: which policies exist, which employees are enrolled.

---

### Phase 11 — Data Acquisition & Seeding

**Step 11.1 — Download real government PDFs**
> Branch: `feat/gov-pdf-download-script` → PR type: Feature (downloaded PDFs stay git-ignored)
- Write `scripts/download_gov_docs.py` to download open-access PDFs from:
  - healthcare.gov (Summary of Benefits and Coverage documents)
  - OPM.gov (Federal Employee Health Benefits plan brochures)
  - DOL.gov (ERISA summaries, compliance guides)
  - CMS.gov (Medicare/Medicaid plan summaries)
- Organize into `data/gov_pdfs/` by source and type.
- Target: 50-100 real documents.

**Step 11.2 — Generate synthetic employer policy docs**
> Branch: `feat/synthetic-document-generator` → PR type: Feature (generated docs stay git-ignored)
- Write `scripts/generate_synthetic_docs.py` that uses LiteLLM to generate:
  - Health plan summaries for 5 fictional employers.
  - Dental and vision plan details.
  - Employee handbooks (benefits section).
  - Open enrollment guides.
  - FAQ documents.
- Convert to PDF/DOCX format.
- Target: 50+ synthetic documents across 5 employers.

**Step 11.3 — Seed script**
> Branch: `feat/seed-data-script` → PR type: Feature
- `scripts/seed_data.py` that creates:
  - 1 admin user (superuser, sees all employers and the admin dashboard).
  - 5 employers with realistic company names.
  - 10-20 employees per employer with randomized enrollments.
  - Policies (health, dental, vision, life, disability) per employer.
  - Triggers Celery ingestion for all seeded documents.

---

### Phase 12 — RAG Evaluation Pipeline

**Step 12.1 — Golden dataset creation**
> Branch: `test/golden-evaluation-dataset` → PR type: Tests
- Manually curate 100+ Q&A pairs in `data/eval/golden_dataset.json`.
- Cover: simple lookups, multi-policy comparisons, personal enrollment queries, edge cases, off-topic rejections.
- Each entry: `{ query, expected_answer, employer_id, policy_type, difficulty }`.

**Step 12.2 — RAGAS evaluation runner**
> Branch: `feat/ragas-evaluation-runner` → PR type: Feature (wires the `rag-eval` CI gate to real thresholds)
- `eval/run_eval.py` that:
  - Loads golden dataset.
  - Runs each query through the full RAG pipeline.
  - Computes RAGAS metrics: faithfulness, answer relevancy, context precision, context recall.
  - Generates a report with pass/fail per metric against configured thresholds.
- Configurable in `eval/eval_config.yaml`.

---

### Phase 13 — Dependency Injection Wiring (Final Review)

> Note: DI wiring happens incrementally throughout development — each adapter is wired into `dependencies.py` as it's built so you can run and test after every phase. This phase is the final audit to ensure every port has its adapter wired and no hardcoded dependencies leaked in.

**Step 13.1 — DI container audit**
> Branch: `refactor/di-container-audit` → PR type: Refactor
- In `api/dependencies.py`, wire all ports to their adapters:
  - `LLMPort` → `LiteLLMAdapter`
  - `VectorStorePort` → `PineconeAdapter`
  - `EventBusPort` → `InMemoryEventBus`
  - `CachePort` → `RedisCacheAdapter`
  - Each repository port → its PostgreSQL adapter.
- Use FastAPI's `Depends()` system for injection.
- Swapping an adapter = changing one line in this file.

---

### Phase 14 — Polish & Production Readiness

**Step 14.1 — Structured logging**
> Branch: `feat/structured-logging` → PR type: Feature
- Set up `structlog` with JSON output.
- Log every API request, LLM call (model, tokens, latency), and Celery task.
- Correlation IDs per request for traceability.

**Step 14.2 — Error handling**
> Branch: `feat/global-error-handling` → PR type: Feature
- Global exception handler in FastAPI.
- Custom exception hierarchy: `DomainException`, `AuthException`, `RateLimitException`, etc.
- User-friendly error messages — never leak stack traces.

**Step 14.3 — Rate limiting**
> Branch: `security/chat-rate-limiting` → PR type: Security
- Per-user rate limiting on chat endpoints (prevent LLM cost abuse).
- Use Redis-backed sliding window.

**Step 14.4 — Retry middleware**
> Branch: `perf/external-call-retries` → PR type: Performance
- Exponential backoff with jitter on all external calls: LLM API, Pinecone, embedding API.
- Configurable max retries and base delay.
- Uses `tenacity` library.

**Step 14.5 — API documentation**
> Branch: `docs/openapi-annotations` → PR type: Docs
- FastAPI auto-generates OpenAPI spec.
- Add descriptions, examples, and response models to every route.
- Separate tag groups: Auth, Chat, Documents, Employers, Employees, Feedback, Admin Analytics, Health.

**Step 14.6 — Environment configs**
> Branch: `chore/environment-profiles` → PR type: Chore
- `.env.example` with every variable documented.
- Separate configs for: `development`, `staging`, `production`.
- Docker Compose profiles for each environment.

**Step 14.7 — Final README update**
> Branch: `docs/final-readme-refresh` → PR type: Docs
- Ensure README.md reflects the complete system: architecture, setup, API reference, data pipeline, model configuration, evaluation.

**Step 14.8 — Release tagging and changelog**
> Branch: `ci/release-automation` → PR type: CI
- Enable the `release.yml` workflow to compute the next semantic version from the Conventional Commit types merged since the last tag.
- Generate `CHANGELOG.md` grouped into Features, Bug Fixes, Performance, Security, and Documentation.
- Create a signed annotated tag (`v1.0.0`) on `main` and publish a GitHub Release with the generated notes.
- Document the hotfix procedure: branch from the release tag, fast-track review, merge back into `main`, and re-tag a patch release.

---

## Data Source Links (Open-Source Policy PDFs)

| Source | URL | Content |
| --- | --- | --- |
| Healthcare.gov SBC | https://www.healthcare.gov/sbc/ | Summary of Benefits & Coverage templates |
| OPM FEHB Plans | https://www.opm.gov/healthcare-insurance/healthcare/plan-information/ | Federal employee health plan brochures |
| DOL ERISA | https://www.dol.gov/agencies/ebsa/laws-and-regulations | Employee benefit compliance docs |
| CMS Medicare | https://www.cms.gov/Medicare/Medicare-General-Information | Medicare plan summaries |
| NY State of Health | https://nystateofhealth.ny.gov/ | State marketplace plan docs |
| CalHR Benefits | https://www.calhr.ca.gov/employees/pages/health-and-wellness.aspx | California state employee benefits |

---

## Future-Proofing Checklist

- [ ] Kafka adapter: implement `KafkaEventBus` fulfilling `EventBusPort`, swap one line in DI.
- [ ] New LLM provider: already handled by LiteLLM config. If LiteLLM itself needs replacing, swap `LiteLLMAdapter` for a new `LLMPort` adapter.
- [ ] New document format (e.g., HTML, Markdown): add one processor class, register in `ProcessorFactory`.
- [ ] New entity (e.g., Dependent, Claim): add domain model, port, adapter, routes — nothing else changes.
- [ ] New feature (e.g., policy comparison, cost calculator): add a new service in `core/services/`, wire through DI.
- [ ] Switch vector DB: implement a new `VectorStorePort` adapter, swap in DI.
- [ ] Switch relational DB: implement new repository adapters, swap in DI.
- [ ] Switch cache: implement new `CachePort` adapter, swap in DI.
- [ ] Add reranking step: insert between retrieval and context assembly in `RAGService` — no other service changes.
- [ ] Add model tier: extend `QueryRouter` config with a new tier — no service changes.
- [ ] Add a deployment environment: add a `deploy-<env>.yml` GitHub Actions workflow triggered by release tags — no branching-model changes.
- [ ] Add a second team: extend `.github/CODEOWNERS` with new path ownership — the branch protection rules stay identical.
- [ ] Move to a monorepo with more packages: keep trunk-based development and extend commit scopes — no long-lived branches introduced.
