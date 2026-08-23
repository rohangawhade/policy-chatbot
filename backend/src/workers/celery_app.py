"""Celery application instance.

No tasks are registered yet — Step 8.1 configures task routing, retries,
and dead-letter handling, and later steps in Phase 8 add the ingestion
tasks. This exists now so the `celery-worker` Docker Compose service has a
real (if empty) app to run.
"""

from celery import Celery

from config import celery_config

app = Celery(
    "policypal",
    broker=celery_config.broker_url,
    backend=celery_config.result_backend,
)
app.conf.broker_connection_retry_on_startup = True
