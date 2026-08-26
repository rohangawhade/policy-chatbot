"""Central `structlog` configuration (files/plan.md Step 14.1,
files/coding-standards.md section 13).

Every adapter/service/worker since Step 3.1 has called
`structlog.get_logger(__name__)`, but nothing ever called
`structlog.configure(...)` -- they've all been running on structlog's
built-in defaults the whole time (Step 3.1's own IMPLEMENTATION_STATUS
entry flagged this as deferred). `configure_logging()` is the one place
that sets real processors/output format for the whole process; call it
once, as early as possible, in every process entry point (`main.py`'s
`create_app()` for the API server, `workers/celery_app.py` at import
time for Celery workers) -- `structlog.get_logger()` calls anywhere else
need no changes, since structlog loggers are lazy proxies that read
whatever configuration is active when a log call actually happens.
"""

import logging
import sys

import structlog

from config import app_config


def configure_logging() -> None:
    """JSON output in production, pretty console output otherwise
    (files/coding-standards.md section 13). `DEBUG`-level logs (internal
    state, variable values) only ever emit when `AppConfig.debug` is set
    -- true by default in dev, expected `false` in production.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    is_production = app_config.env == "production"
    if is_production:
        # JSON output has no other way to represent a traceback -- it must
        # be pre-formatted into a plain string field before `JSONRenderer`
        # serializes the event dict.
        shared_processors.append(structlog.processors.format_exc_info)
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if is_production
        # `ConsoleRenderer` renders `exc_info` itself (its own colorized/
        # `rich`-aware traceback formatter) -- pairing it with
        # `format_exc_info` above would pre-flatten the traceback into a
        # string first, defeating that, and `structlog` warns on every
        # `logger.exception(...)` call about exactly this combination.
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if app_config.debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        # Real, empirically-found gotcha, not a stylistic choice:
        # `cache_logger_on_first_use=True` freezes a module-level
        # `logger = structlog.get_logger(__name__)` singleton's processor
        # chain the *first* time it actually logs anything, permanently --
        # later `structlog.configure(...)` calls (e.g. this function itself,
        # called again with a different `app_config.env`/`debug`, or a
        # test's `structlog.testing.capture_logs()`) have no effect on an
        # already-cached logger. Every adapter/service/worker in this
        # codebase uses exactly that module-level-singleton pattern, so
        # caching here would make reconfiguration silently no-op for
        # whichever loggers happened to log first -- confirmed via this
        # step's own test suite, where `workers/celery_app.py` importing
        # (and calling `configure_logging()`) during pytest's collection
        # phase caused every route-test file's `RequestLoggerMiddleware`
        # logger to freeze against that config before any of this step's
        # own log-capturing tests could run.
        cache_logger_on_first_use=False,
    )
