"""Celery application instance.

No tasks are registered yet — Step 8.1 configures task routing, retries,
and dead-letter handling, and later steps in Phase 8 add the ingestion
tasks. This exists now so the `celery-worker` Docker Compose service has a
real (if empty) app to run.
"""

import os

from celery import Celery

app = Celery(
    "policypal",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
)
app.conf.broker_connection_retry_on_startup = True
