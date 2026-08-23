# PolicyPal — Coding Standards & Best Practices

## This file is the single source of truth for code quality in this project. Every piece of code written must follow these rules.

---

## 0. ABSOLUTE RULES

### Never Commit Directly to `main`
Every change ships on its own short-lived branch and merges into `main` through a reviewed pull request. `main` is protected, always green, and always releasable. Branch names follow `<type>/<scope>-<short-kebab-summary>` where `<type>` is one of `feat`, `fix`, `hotfix`, `refactor`, `perf`, `test`, `docs`, `chore`, `build`, `ci`, `security`, or `revert`. Push the feature branch, never `main`. Full branching, commit, PR, and release rules live in the Git Workflow section of `files/plan.md` and are summarized in section 13 below.

### Never Commit Secrets
`.env`, API keys, private keys, tokens, credentials, and generated document corpora are never committed. `gitleaks` runs as a pre-commit hook and as a required CI check. A secret that reaches a branch must be rotated, not just deleted from history.

### README.md Must Stay Updated
Every time code is added, modified, or deleted, the `README.md` must be updated in the same step to reflect the change. The README is the living documentation of the project. If a new service is added, the README explains what it does in plain English. If a config value is added, the README's setup section reflects it. If a feature is completed, the README's feature list updates. No code change is complete until the README matches reality.

---

## 1. SOLID Principles (Non-Negotiable)

### S — Single Responsibility Principle
Every class and function does exactly one thing. If you're writing a docstring that contains the word "and", the function is doing too much.

```python
# WRONG — does two things
class DocumentService:
    def upload_and_process_document(self, file):
        self._save_to_disk(file)
        self._extract_text(file)
        self._chunk_and_embed(file)

# RIGHT — each method has one job, orchestration is separate
class DocumentService:
    def __init__(self, processor: DocumentProcessorPort, chunker: ChunkerPipeline, embedder: EmbeddingService):
        self._processor = processor
        self._chunker = chunker
        self._embedder = embedder

    def ingest(self, file: UploadedFile) -> DocumentId:
        raw_text = self._processor.extract_text(file)
        chunks = self._chunker.process(raw_text, file.metadata)
        self._embedder.embed_and_store(chunks)
        return file.id
```

### O — Open/Closed Principle
Code is open for extension, closed for modification. Adding a new document type, LLM provider, or event handler must never require changing existing working code.

```python
# WRONG — adding a new format requires modifying this function
def process_document(file):
    if file.ext == "pdf":
        return process_pdf(file)
    elif file.ext == "docx":
        return process_docx(file)
    # every new format = another elif here

# RIGHT — factory + strategy pattern
class ProcessorFactory:
    _processors: dict[str, type[DocumentProcessorPort]] = {}

    @classmethod
    def register(cls, ext: str, processor: type[DocumentProcessorPort]):
        cls._processors[ext] = processor

    @classmethod
    def get(cls, ext: str) -> DocumentProcessorPort:
        if ext not in cls._processors:
            raise UnsupportedFormatError(ext)
        return cls._processors[ext]()

# Adding XML support = one new class + one registration line. Zero changes to existing code.
```

### L — Liskov Substitution Principle
Every adapter that implements a port must be fully interchangeable with any other adapter for that port. No surprises, no special cases.

```python
# If PineconeAdapter implements VectorStorePort, and tomorrow you write
# ChromaAdapter implementing VectorStorePort, every service that depends
# on VectorStorePort must work identically with either. No "if isinstance" checks.
```

### I — Interface Segregation Principle
Ports must be small and focused. A class should never be forced to implement methods it doesn't use.

```python
# WRONG — one giant interface
class StoragePort(ABC):
    def upsert_vector(self): ...
    def query_vector(self): ...
    def save_to_db(self): ...
    def get_from_db(self): ...

# RIGHT — separate interfaces
class VectorStorePort(ABC):
    def upsert(self): ...
    def query(self): ...

class RepositoryPort(ABC):
    def save(self): ...
    def get(self): ...
```

### D — Dependency Inversion Principle
Core services depend on abstractions (ports), never on concrete implementations (adapters). Imports flow inward only.

```python
# WRONG — core service imports a specific adapter
from adapters.vector_store.pinecone_adapter import PineconeAdapter

class RAGService:
    def __init__(self):
        self.store = PineconeAdapter()  # tight coupling

# RIGHT — core service depends on the port
from core.ports.vector_store_port import VectorStorePort

class RAGService:
    def __init__(self, store: VectorStorePort):  # injected
        self._store = store
```

---

## 2. ACID Compliance (Database Operations)

### Atomicity
A database operation either fully completes or fully rolls back. Use SQLAlchemy's session as a Unit of Work.

```python
async def enroll_employee_in_policy(self, employee_id: str, policy_id: str):
    async with self._session_factory() as session:
        async with session.begin():  # auto-rollback on exception
            employee = await self._employee_repo.get(session, employee_id)
            policy = await self._policy_repo.get(session, policy_id)
            enrollment = Enrollment(employee=employee, policy=policy)
            session.add(enrollment)
        # commit happens here — or full rollback if anything above threw
```

### Consistency
All database constraints (foreign keys, unique indexes, check constraints) are enforced at the DB level, not just in application code. Never trust the app layer alone.

### Isolation
Use appropriate transaction isolation levels. Default to `READ COMMITTED` for most operations. Use `SERIALIZABLE` for financial or enrollment-critical operations where race conditions would corrupt data.

### Durability
PostgreSQL handles this. Ensure WAL (Write-Ahead Logging) is enabled in production. Never use `synchronous_commit = off` for critical data.

---

## 3. Import Rules (Strict Boundary Enforcement)

```
core/domain/     → imports NOTHING from outside core/
core/ports/      → imports only from core/domain/
core/services/   → imports from core/ports/ and core/domain/ ONLY
adapters/        → imports from core/ports/, core/domain/, and external libraries
api/             → imports from core/services/, core/domain/, and adapters (for DI wiring only)
```

If you find yourself importing from `adapters/` inside `core/`, you are violating the architecture. Stop and refactor.

---

## 4. Naming Conventions

### Python (Backend)
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_single_leading_underscore`
- ABCs (ports): suffix with `Port` (e.g., `LLMPort`, `VectorStorePort`)
- Implementations (adapters): suffix with `Adapter` (e.g., `LiteLLMAdapter`, `PineconeAdapter`)
- Repository implementations: suffix with `Repository` (e.g., `PostgresEmployerRepository`)

### TypeScript (Frontend)
- Files: `PascalCase.tsx` for components, `camelCase.ts` for utilities
- Components: `PascalCase`
- Functions/hooks: `camelCase`, hooks prefixed with `use`
- Types/interfaces: `PascalCase`, no `I` prefix
- Constants: `UPPER_SNAKE_CASE`

---

## 5. Type Safety

### Python
- Every function must have complete type annotations — parameters and return type.
- Use `Pydantic BaseModel` for all API request/response schemas.
- Use `TypeVar` and `Generic` for generic repository interfaces.
- No `Any` type unless absolutely unavoidable (and add a comment explaining why).

```python
# WRONG
def get_chunks(query, k):
    ...

# RIGHT
async def get_chunks(query: str, k: int = 5) -> list[DocumentChunk]:
    ...
```

### TypeScript
- `strict: true` in `tsconfig.json`. No exceptions.
- No `any` type. Use `unknown` if the type is genuinely unknown, then narrow it.
- All API responses typed with interfaces matching the backend Pydantic schemas.

---

## 6. Error Handling

### Custom Exception Hierarchy

```python
class PolicyPalError(Exception):
    """Base exception for all app errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code

class DomainError(PolicyPalError):
    """Business rule violation."""

class NotFoundError(PolicyPalError):
    """Requested entity does not exist."""

class AuthorizationError(PolicyPalError):
    """User lacks permission for this action."""

class TenantAccessError(AuthorizationError):
    """User tried to access another employer's data."""

class DocumentProcessingError(PolicyPalError):
    """Document ingestion or parsing failed."""

class RateLimitError(PolicyPalError):
    """User exceeded allowed request rate."""

class ModelUnavailableError(PolicyPalError):
    """Requested LLM model tier is not configured or unreachable."""
```

### Rules
- Never catch bare `Exception` unless re-raising. Catch specific exceptions.
- Never swallow exceptions silently. Log them at minimum.
- API layer converts domain exceptions to appropriate HTTP status codes.
- Never expose internal error details (stack traces, SQL queries) to the client.
- Model fallback: catch `ModelUnavailableError` in the query router and fall back to the cheap model tier. Never crash because a model is missing.

---

## 7. API Design

### RESTful conventions
- `GET` for reads, `POST` for creates, `PUT` for full updates, `PATCH` for partial updates, `DELETE` for removals.
- Plural nouns for resources: `/api/documents`, `/api/employers`, `/api/conversations`.
- Nested resources where ownership is clear: `/api/conversations/{id}/messages`.
- Always return consistent response envelopes.

### Response format

```python
class APIResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ErrorDetail | None = None
    meta: dict | None = None  # pagination, etc.
```

### Pagination
- Cursor-based for conversations/messages (real-time data).
- Offset-based for admin lists (documents, employers).

### Status codes
- `200` success, `201` created, `204` deleted.
- `400` bad request, `401` unauthenticated, `403` forbidden, `404` not found, `422` validation error, `429` rate limited.
- `500` only for genuine unexpected errors.

---

## 8. Security

- JWT access tokens expire in 15 minutes. Refresh tokens expire in 7 days.
- Passwords hashed with bcrypt (minimum 12 rounds).
- All user input validated via Pydantic before it reaches any service.
- SQL injection prevented by always using parameterized queries (SQLAlchemy handles this — never use raw string interpolation).
- Tenant isolation enforced at the repository level — every query includes `employer_id` filter. No optional scoping.
- File uploads validated: check MIME type, file extension, and file size limits before processing.
- Rate limiting on all LLM-calling endpoints.
- CORS configured to allow only the frontend origin.

---

## 9. Async Patterns

- All I/O-bound operations must be `async`: database queries, HTTP calls to LLM APIs, vector store operations.
- CPU-bound work (chunking, heavy text processing) goes to Celery workers, not the async event loop.
- Never use `time.sleep()` in async code. Use `asyncio.sleep()` if a delay is truly needed.
- Use `asyncio.gather()` for parallel independent operations (e.g., fetching chunks + user enrollment simultaneously).

---

## 10. Configuration

- All configuration via environment variables. No hardcoded values for anything that could change between environments.
- Pydantic `BaseSettings` for typed, validated config.
- Secrets (API keys, DB passwords) never committed. `.env` in `.gitignore`.
- Feature flags as env vars for gradual rollouts.

```python
class LLMConfig(BaseSettings):
    cheap_model: str = "claude-haiku-4-5-20251001"
    powerful_model: str | None = None  # None = all queries go to cheap model
    embedding_model: str = "text-embedding-3-small"  # separate from generation models
    complexity_threshold: float = 0.4
    temperature: float = 0.1
    max_tokens: int = 2048
    streaming_enabled: bool = True
    fallback_enabled: bool = True  # auto-fallback to cheap if powerful fails

    model_config = SettingsConfigDict(env_prefix="LLM_")
```

---

## 11. Retry & Resilience

All external service calls (LLM API, Pinecone, embedding API) must use retry with exponential backoff.

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
)
async def call_llm(self, prompt: str, model: str) -> str:
    ...
```

### Rules
- Max 3 retries for LLM calls, 3 for Pinecone, 2 for embedding.
- Exponential backoff with jitter to avoid thundering herd.
- Circuit breaker pattern for sustained failures (if a model is down for 5+ consecutive calls, stop trying for 60 seconds).
- Always log retry attempts with the attempt number and error.

---

## 12. Analytics Event Logging

Every LLM call, retrieval, guardrail action, and user interaction must emit an analytics event. These events are the data source for the admin dashboard — if an event isn't logged, it doesn't exist for the admin.

### What Must Be Logged

```python
# Every LLM call → LLMCostLog
LLMCostLog(
    model="claude-haiku-4-5-20251001",
    input_tokens=1200,
    output_tokens=450,
    estimated_cost_usd=0.0023,     # calculated from model pricing config
    employer_id="emp_123",
    query_complexity_score=0.3,
    model_tier="cheap",             # or "powerful"
    timestamp=datetime.utcnow(),
)

# Every chat request → RequestLatencyLog
RequestLatencyLog(
    total_ms=1820,
    retrieval_ms=340,              # Pinecone query time
    llm_ms=1400,                   # LLM generation time
    overhead_ms=80,                # everything else
    model_tier="cheap",
    employer_id="emp_123",
    timestamp=datetime.utcnow(),
)

# Low confidence retrieval → FlaggedResponse
FlaggedResponse(
    conversation_id="conv_456",
    message_id="msg_789",
    query_text="what's my HSA limit?",
    top_similarity_score=0.42,     # below confidence threshold
    flag_reason="low_retrieval_confidence",
    status="pending_review",       # pending_review | reviewed | dismissed
    employer_id="emp_123",
)

# Guardrail rejection → GuardrailRejection
GuardrailRejection(
    query_text="what's the weather today?",
    rejection_reason="off_topic",
    employer_id="emp_123",
    timestamp=datetime.utcnow(),
)
```

### Rules
- Analytics logging must NEVER block the main request. Log asynchronously (fire-and-forget to the event bus, handled by a subscriber that writes to PostgreSQL).
- If analytics logging fails, the user's request still succeeds. Analytics are observability, not business logic.
- Cost estimation uses a configurable pricing table per model — update when provider prices change.
- Confidence threshold for auto-flagging is configurable (default: flag when top retrieved chunk similarity < 0.5).

---

## 13. Application Logging

- Use `structlog` with JSON output in production, pretty-print in dev.
- Every log entry includes: `timestamp`, `level`, `correlation_id`, `employer_id`, `user_id`.
- Log at appropriate levels:
  - `DEBUG`: internal state, variable values (dev only).
  - `INFO`: request received, task started/completed, document processed, model routed.
  - `WARNING`: rate limit approached, retry triggered, model fallback activated.
  - `ERROR`: operation failed but system continues.
  - `CRITICAL`: system cannot continue (DB down, Pinecone unreachable).
- Never log secrets, tokens, passwords, or full user queries (PII risk). Log query length and topic category instead.

---

## 14. README.md Rules

The README is a living document. It must always reflect the current state of the codebase.

### Structure

```markdown
# PolicyPal

One-line description.

## What This Project Does
Plain English explanation of the system. No jargon. A non-developer should understand what the app does after reading this section.

## Architecture Overview
Brief explanation of how the pieces fit together. Include the ASCII diagram from the plan.

## Features
Checklist of what's built and what's pending. Update as features are completed.

## Tech Stack
Table of technologies used and why.

<details>
<summary>🛠️ Prerequisites</summary>
Exact software and versions needed (Docker, Node, Python, etc.)
</details>

<details>
<summary>📦 Environment Setup</summary>
Step-by-step: clone, copy .env, fill in API keys — with exact commands.
</details>

<details>
<summary>🐳 Running with Docker</summary>
Exact docker compose commands, what to expect, how to verify it's working.
</details>

<details>
<summary>🗄️ Database Setup</summary>
Migration commands, seed data commands, how to verify tables exist.
</details>

<details>
<summary>📄 Loading Documents</summary>
How to download gov PDFs, generate synthetic docs, trigger ingestion.
</details>

<details>
<summary>🔑 API Keys & Model Configuration</summary>
Which API keys are needed, where to get them, how to configure model tiers.
Every env var documented: name, purpose, example value, required/optional.
</details>

<details>
<summary>🧪 Running RAG Evaluation</summary>
How to run the eval pipeline, interpret results, add golden Q&A pairs.
</details>

<details>
<summary>🔧 Common Issues & Troubleshooting</summary>
Known issues and their fixes. Updated as issues are discovered.
</details>

## API Endpoints
Summary table of all endpoints with method, path, auth requirement, and description.

## Project Structure
Abbreviated folder tree with one-line descriptions of key files.

## How It Works (Layman's Terms)
A section explaining the entire flow — from document upload to chat response — in simple, non-technical language. Updated whenever the flow changes.
```

### Update Rules
- New file/module added → update Project Structure section.
- New API endpoint added → update API Endpoints table.
- New env var added → update the API Keys / Environment Setup collapsible.
- Feature completed → check it off in Features list.
- Bug found and fixed → add to Troubleshooting if it might recur.
- Architecture change → update Architecture Overview and How It Works.
- New dependency added → update Tech Stack and Prerequisites.

---

## 15. Docstrings

Every public class and function gets a docstring. Use Google style.

```python
class RAGService:
    """Orchestrates the retrieval-augmented generation pipeline.

    Handles query preprocessing, vector search, context assembly,
    and streaming LLM response generation. All operations are scoped
    to the authenticated user's employer.

    Attributes:
        llm: LLM provider for generation and embedding.
        vector_store: Vector database for semantic search.
        conversation_repo: Persistence for chat history.
    """

    async def query(self, user_query: str, conversation_id: str) -> AsyncIterator[str]:
        """Process a user query and stream the response.

        Args:
            user_query: The natural language question from the user.
            conversation_id: ID of the current conversation for context.

        Yields:
            Response tokens as they are generated.

        Raises:
            DomainError: If the query is outside the policy domain.
            TenantAccessError: If tenant context is missing.
        """
```

---

## 16. Dependency Management

- Pin all dependency versions in `pyproject.toml` and `package.json`.
- Use lockfiles: `poetry.lock` or `pip-compile` output for Python, `package-lock.json` for Node.
- Separate dev dependencies from production dependencies.
- Audit dependencies periodically for vulnerabilities.

---

## 17. Future-Proofing Patterns

### Event Bus Abstraction (Kafka-Ready)

```python
# The port
class EventBusPort(ABC):
    @abstractmethod
    async def publish(self, event: DomainEvent) -> None: ...

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable) -> None: ...

# Today's adapter — in-memory
class InMemoryEventBus(EventBusPort):
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    async def publish(self, event: DomainEvent) -> None:
        for handler in self._handlers.get(event.event_type, []):
            await handler(event)

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._handlers[event_type].append(handler)

# Tomorrow's adapter — Kafka (zero changes to any service)
class KafkaEventBus(EventBusPort):
    def __init__(self, bootstrap_servers: str):
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
        self._consumer = AIOKafkaConsumer(bootstrap_servers=bootstrap_servers)

    async def publish(self, event: DomainEvent) -> None:
        await self._producer.send(event.event_type, event.serialize())

    def subscribe(self, event_type: str, handler: Callable) -> None:
        # register consumer group handler
        ...
```

### Multi-Model Fallback Pattern

```python
class QueryRouter:
    """Routes queries to appropriate model tier with automatic fallback."""

    def __init__(self, config: LLMConfig):
        self._config = config

    def select_model(self, complexity_score: float) -> str:
        if self._config.powerful_model and complexity_score >= self._config.complexity_threshold:
            return self._config.powerful_model
        return self._config.cheap_model

    def fallback_model(self) -> str:
        """Always returns the cheap model. Called when the primary selection fails."""
        return self._config.cheap_model

# Usage in RAGService:
# model = router.select_model(score)
# try:
#     response = await llm.generate(prompt, model=model)
# except ModelUnavailableError:
#     response = await llm.generate(prompt, model=router.fallback_model())
```

### Extensible Entity Pattern

When adding a new entity (e.g., `Dependent`, `Claim`):
1. Add domain model in `core/domain/`.
2. Add repository port in `core/ports/`.
3. Add service in `core/services/` (depends only on ports).
4. Add ORM model + repository adapter in `adapters/persistence/`.
5. Add routes in `api/routes/`.
6. Register in DI container.
7. Update README.md.
8. Nothing else changes.

---

## 18. Code Smells to Reject

- Functions longer than 30 lines → split.
- More than 3 parameters → use a config/params object.
- Nested `if` deeper than 2 levels → refactor to early returns or extract methods.
- Comments explaining "what" → rewrite the code to be self-documenting. Comments should only explain "why".
- Magic numbers or strings → extract to named constants or config.
- Copy-pasted logic → extract to a shared utility or base class.
- `isinstance` checks in services → you're violating polymorphism. Use the port interface.
- Direct adapter imports in core → architecture violation. Use dependency injection.
- README out of date → code change is incomplete. Update it.
- Committing straight to `main`, or a branch named `test`, `tmp`, or `mybranch` → rejected.
- A PR mixing a feature, a bug fix, and a dependency bump → split into separate typed PRs.

---

## 19. Git & Version Control Standards

Git is part of the definition of done. Code that is not on a pushed branch with an open pull request is not finished.

### Branching
- Trunk-based development. `main` is the only long-lived branch, and it is protected.
- One logical change per branch. Branches live hours to days, never weeks.
- Naming: `<type>/<scope>-<short-kebab-summary>` — for example `feat/rag-streaming-generation`, `fix/sse-stream-not-closing`, `security/tenant-isolation-audit`.
- Rebase onto `main` to stay current. Never merge `main` into your branch.
- Delete the branch immediately after merge.

### Commits
- Conventional Commits format: `<type>(<scope>): <imperative summary>`.
- Allowed types: `feat`, `fix`, `hotfix`, `refactor`, `perf`, `test`, `docs`, `chore`, `build`, `ci`, `security`, `revert`.
- Breaking changes use `!` after the type or a `BREAKING CHANGE:` footer.
- Commits must be atomic and individually buildable. Squash `wip` commits before opening the PR.
- Signed commits are required on `main`.

### Pull Requests
- PR title uses the same Conventional Commits format, because it becomes the squash-merge commit message.
- The branch prefix determines the PR template, the PR label, and the CI jobs that run.
- Target under 400 changed lines. Split larger work into stacked PRs.
- Required in every PR: what changed, why, how it was validated, linked issue, and a rollback note for auth, tenancy, migration, or RAG changes.
- UI changes require screenshots. Performance changes require before/after numbers. Bug fixes require a regression test that fails without the fix.
- Two approvals are required for auth, tenant isolation, and database migration changes, enforced through `CODEOWNERS`.

### Merging
- Squash and merge only. Linear history on `main`.
- All required checks must be green: lint, typecheck, tests, Docker build, migration check, secret scan, dependency audit, and the RAG evaluation gate when retrieval or prompt files change.
- Never merge with failing or skipped checks. Never use force-push on `main`.

### Releases
- Semantic Versioning, derived from merged commit types: `feat` bumps MINOR, `fix`/`perf`/`security` bump PATCH, `BREAKING CHANGE` bumps MAJOR.
- Tags are signed and annotated. `CHANGELOG.md` is generated from commit history, never hand-edited.
- Hotfixes branch from the release tag, get fast-tracked review, and are merged back into `main` the same day.
