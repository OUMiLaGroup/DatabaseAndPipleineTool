"""
One logging setup for every service (backend and workers).

Usage at the top of a worker's main.py:

    from utilities.logging_utilities import configure_logging
    logger = configure_logging("cvat_worker")

Every line then looks like:

    2026-10-16 14:02:11,512 ERROR [cvat_worker] Failed job_run(route=... segment=3) ...
    2026-10-16 14:02:11,498 INFO [cvat_worker] [services.cvat_service] Restarting cvat_server container
    Traceback (most recent call last): ...

Set LOG_LEVEL=DEBUG in the environment for more detail.

Logging rules for this codebase:
* Inside an ``except`` block use ``logger.exception("what failed", ...)`` so the traceback is kept.
* Never pass the exception as an extra argument without a %s placeholder
  (``logging.error(f"...", e)``): logging cannot format it and the real error is lost.
* Use %-style arguments (``logger.info("route=%s", route_id)``) rather than f-strings.
"""
import logging
import os

LOG_FORMAT = "%(asctime)s %(levelname)s [%(service)s]%(origin)s %(message)s"

# Libraries that are very chatty at INFO level
_NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "botocore")


class _ServiceNameFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "service"):
            record.service = self.service_name
        # Show which module logged the line, unless it is the service's own logger
        record.origin = "" if record.name == self.service_name else f" [{record.name}]"
        return True


def configure_logging(service_name: str, level: str | int | None = None) -> logging.Logger:
    """Configure the root logger for this process and return a logger for the service."""
    resolved_level = level if level is not None else os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=resolved_level, format=LOG_FORMAT, force=True)

    service_filter = _ServiceNameFilter(service_name)
    for handler in logging.getLogger().handlers:
        handler.addFilter(service_filter)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    return logging.getLogger(service_name)
