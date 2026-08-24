from typing import Any

import pytest
from celery import Celery

from workers import celery_app as celery_app_module
from workers.celery_app import app


def test_celery_app_is_configured() -> None:
    assert isinstance(app, Celery)
    assert app.main == "policypal"
    assert app.conf.broker_connection_retry_on_startup is True


def test_task_default_queue_is_default() -> None:
    assert app.conf.task_default_queue == "default"


def test_embedding_tasks_are_routed_to_the_embedding_queue() -> None:
    assert app.conf.task_routes["embedding.*"] == {"queue": "embedding"}


def test_task_failure_signal_is_connected_to_the_dead_letter_handler() -> None:
    from celery.signals import task_failure

    receiver_functions = [ref() for _key, ref in task_failure.receivers]
    assert celery_app_module._route_to_dead_letter in receiver_functions


def test_dead_letter_handler_republishes_the_failed_task_to_the_dead_letter_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send_task_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        app,
        "send_task",
        lambda name, args=None, kwargs=None, queue=None: send_task_calls.append(
            {"name": name, "args": args, "kwargs": kwargs, "queue": queue}
        ),
    )

    class _FakeTask:
        name = "embedding.embed_and_index_document"

    celery_app_module._route_to_dead_letter(
        sender=_FakeTask(),
        task_id="task-123",
        exception=ValueError("boom"),
        args=(1, 2),
        kwargs={"a": "b"},
    )

    assert send_task_calls == [
        {
            "name": "embedding.embed_and_index_document",
            "args": (1, 2),
            "kwargs": {"a": "b"},
            "queue": "dead_letter",
        }
    ]


def test_dead_letter_handler_without_a_sender_does_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send_task_calls: list[Any] = []
    monkeypatch.setattr(app, "send_task", lambda *a, **kw: send_task_calls.append((a, kw)))

    celery_app_module._route_to_dead_letter(sender=None, task_id="task-123")

    assert send_task_calls == []
