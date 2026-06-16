"""Centralised logging configuration.

Replaces the noisy SQLAlchemy `echo` SQL dump with a clean, structured log
stream focused on what's actually useful in production: who is using the app,
which endpoints they hit, how long requests take, and key business events
(sessions started/submitted, reports generated).

Call `setup_logging()` once at startup, before the app starts serving.
"""
import logging
import sys

# A request-scoped marker so business-event logs can be correlated to the
# HTTP request that produced them. Set by the access-log middleware.
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    """Inject the current request id into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


_LOG_FORMAT = "%(asctime)s %(levelname)-5s [%(request_id)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    # Silence the per-statement SQL dump. WARNING still surfaces real DB
    # problems (pool exhaustion, disconnects) without the cached-query noise.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    # Uvicorn's default access log ("INFO: 1.2.3.4 - GET /x 200") is replaced
    # by our richer access middleware, so quiet the built-in one.
    logging.getLogger("uvicorn.access").handlers[:] = []
    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("uvicorn.error").handlers[:] = []
    logging.getLogger("uvicorn.error").propagate = True

    # Third-party libraries that like to chatter at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
