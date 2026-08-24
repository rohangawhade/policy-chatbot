"""Celery application instance.

Step 4.4 registers the first task (`workers/embedding_task.py`). Task
routing, retries, and dead-letter handling are still Step 8.1's job —
this app runs on Celery's defaults until then. This module existed with
no tasks from Step 1.2 onward so the `celery-worker` Docker Compose
service always had a real app to run.

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

from celery import Celery

from config import celery_config

app = Celery(
    "policypal",
    broker=celery_config.broker_url,
    backend=celery_config.result_backend,
    include=["workers.embedding_task"],
)
app.conf.broker_connection_retry_on_startup = True
