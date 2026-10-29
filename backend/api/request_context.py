"""
Per-request context for the API.

Every request gets a request ID (taken from an incoming ``X-Request-ID`` header, or
generated). The ID is:

* returned to the client in the ``X-Request-ID`` response header and in every error body,
* attached to every log line written while the request is being handled.

If someone reports an error, ask for the request ID shown in the UI and run:

    docker compose logs backend | grep <request_id>
"""
import logging
from contextvars import ContextVar
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id(incoming: str | None = None) -> str:
    # Accept a client-provided ID only if it looks sane, otherwise generate one
    if incoming and len(incoming) <= 64 and incoming.replace("-", "").isalnum():
        return incoming
    return uuid4().hex[:12]


def set_request_id(request_id: str):
    return _request_id.set(request_id)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


class RequestIdLogFilter(logging.Filter):
    """Adds ``record.request_id`` so log formats can include ``%(request_id)s``."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_api_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] [req=%(request_id)s] %(message)s",
        force=True,  # replace any handlers a library configured before us
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdLogFilter())
