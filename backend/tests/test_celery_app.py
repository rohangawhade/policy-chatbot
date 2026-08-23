from celery import Celery

from workers.celery_app import app


def test_celery_app_is_configured() -> None:
    assert isinstance(app, Celery)
    assert app.main == "policypal"
    assert app.conf.broker_connection_retry_on_startup is True
