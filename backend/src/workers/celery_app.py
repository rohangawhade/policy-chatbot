"""Celery application instance.

Step 1.2 created this module with no tasks (so the `celery-worker`
Docker Compose service always had a real app to run); Step 4.4
registered the first task. This step (8.1) adds the app-wide
infrastructure every task family builds on: queue routing and
dead-letter handling. Retry policy is deliberately *not* set here —
see the comment above `task_routes` below.

`include` lists every module that defines `@app.task`-decorated tasks.
`workers/embedding_task.py` imports `app` from *this* module to decorate
its task, so this module can't import it back directly without a
circular import — `include` is Celery's own answer to exactly this:
it imports each listed module once, after `app` already exists, purely
for its task-registration side effect. Without it, a worker started as
`celery -A workers.celery_app worker` never imports `embedding_task.py`
at all, so the task silently never registers (caught by inspecting a
running worker's `[tasks]` list, which was empty until this was added).
"""

from typing import Any

import structlog
from celery import Celery
from celery.signals import task_failure

from config import celery_config
from logging_config import configure_logging

# Celery workers are a separate process from the API server -- `main.py`'s
# `create_app()` never runs here, so this module (imported once per worker
# process via `celery -A workers.celery_app worker`) is this process's own
# entry point for Step 14.1's central structlog setup.
configure_logging()

logger = structlog.get_logger(__name__)

app = Celery(
    "policypal",
    broker=celery_config.broker_url,
    backend=celery_config.result_backend,
    include=["workers.embedding_task", "workers.document_ingestion_task"],
)
app.conf.broker_connection_retry_on_startup = True

# Queue routing: every task name in this app follows a
# "<family>.<action>" convention (e.g. `embedding.embed_and_index_document`),
# routed here by family prefix to its own queue. A new task family adds
# one more `task_routes` entry — nothing else in this file changes. The
# worker process must also be told to consume the new queue (`-Q` in
# docker-compose.yml/.override.yml's `celery-worker` command) — a queue
# with no consumer just accumulates unprocessed tasks silently, so this
# is a two-place change, easy to half-do; both compose files were
# updated alongside this.
app.conf.task_default_queue = "default"
app.conf.task_routes = {
    "embedding.*": {"queue": "embedding"},
    "ingestion.*": {"queue": "ingestion"},
}

# Retries: deliberately not a blind app-wide default here (a task that
# always retries the exact same failure 3 times, e.g. a malformed
# document, just delays reaching dead-letter for no benefit). Every task
# declares its own `autoretry_for`/`retry_backoff`/`retry_kwargs` on its
# `@app.task(...)` decorator instead — see `workers/embedding_task.py`
# for the first concrete example. This is a *task-level* retry (whole
# attempt, minutes-scale backoff, for failures the per-call tenacity
# retries inside each port adapter didn't already absorb), layered above
# — not a replacement for — those existing per-call retries.


@task_failure.connect  # type: ignore[misc]
# `task_failure` resolves to `Any` (celery.* has no stubs, per
# pyproject.toml's ignore_missing_imports override) — mypy strict's
# disallow_untyped_decorators still flags decorating with an Any-typed
# callable itself, same situation as `@app.task(...)` in embedding_task.py.
def _route_to_dead_letter(
    sender: Any = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    **_extra: Any,
) -> None:
    """Celery + Redis has no built-in dead-letter queue (that's a
    RabbitMQ concept) — this is the app's own. `task_failure` fires
    exactly once per task, only once every retry declared on that
    task's own decorator has been exhausted (Celery never fires it for
    an attempt it's still going to retry) — so every call here already
    represents a genuine, final failure, not a transient one.

    Re-publishes the exact same task (name/args/kwargs) to a
    `dead_letter` queue that nothing consumes by default, so a failure
    is never silently dropped — it can be inspected or manually
    replayed later with `celery -A workers.celery_app worker -Q
    dead_letter`.
    """
    if sender is None:
        return
    logger.error(
        "task_failed_routing_to_dead_letter",
        task_name=sender.name,
        task_id=task_id,
        error=str(exception),
    )
    app.send_task(sender.name, args=args, kwargs=kwargs, queue="dead_letter")
