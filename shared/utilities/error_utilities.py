"""
Helpers for turning exceptions into error messages that are stored in the database
(routes.error, segments.error, job_runs.error, job_segment_run.error, ...) and shown in the UI.
"""
import errno
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from services.errors import PipelineError

# Error columns are plain strings; keep them readable in the UI
MAX_ERROR_LENGTH = 1000

_KNOWN_HINTS: list[tuple[type[BaseException], str]] = [
    (SQLAlchemyError, "Check that the postgres container is running and healthy (docker compose ps)."),
    (TimeoutError, "A service took too long to respond. Check that MinIO and CVAT are running, then retry."),
    (ConnectionError, "Could not connect to a service. Check that MinIO, Postgres and CVAT are running (docker compose ps)."),
]


def error_code_of(exc: BaseException) -> str | None:
    """The stable error code for audit logs, e.g. "COMMA_AUTH_FAILED", or None for unexpected errors."""
    return exc.code if isinstance(exc, PipelineError) else None


def describe_exception(exc: BaseException, max_length: int = MAX_ERROR_LENGTH) -> str:
    """Return a short, human-readable description of an exception, including a fix hint when known.

    Examples:
        "Route abc not found | How to fix: Check the route ID ..."
        "RuntimeError: extraction exited with code 1 for route abc/3"
    """
    hint: str | None = None
    if isinstance(exc, PipelineError):
        text = exc.message
        hint = exc.hint
    else:
        message = str(exc).strip()
        text = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
        if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
            hint = "The disk is full. Free up space (e.g. docker system prune, clear ./data) and retry."
        else:
            hint = next((h for exc_type, h in _KNOWN_HINTS if isinstance(exc, exc_type)), None)

    if hint:
        text = f"{text} | How to fix: {hint}"
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."
    return text


async def record_failure(
    session: AsyncSession,
    logger: logging.Logger,
    description: str,
    write_failure: Callable[[], Awaitable[object]],
) -> None:
    """Persist a failure (e.g. set status FAILED + error message) without crashing the worker.

    * If the failing code left the session unusable (a database error), it is rolled back first.
      Note that a rollback expires loaded ORM objects, so ``write_failure`` should look rows up
      by their IDs rather than reuse objects loaded before the failure.
    * If recording the failure itself fails, that is logged and the worker keeps running.
    """
    try:
        if not session.is_active:
            await session.rollback()
        await write_failure()
        await session.commit()
    except Exception:
        logger.exception("Could not record failure for %s", description)
        try:
            await session.rollback()
        except Exception:
            logger.exception("Rollback failed while recording failure for %s", description)


def summarize_segment_failures(
    failures: dict[int, str | None],
    total: int,
    action: str = "failed",
    max_length: int = MAX_ERROR_LENGTH,
) -> str:
    """One-line summary like "2 of 10 segments failed (segments: 3, 7). First error (segment 3): ..."."""
    failed_ids = ", ".join(str(segment_id) for segment_id in sorted(failures))
    first_segment = min(failures)
    first_error = failures[first_segment] or "no reason recorded"
    text = (
        f"{len(failures)} of {total} segments {action} (segments: {failed_ids}). "
        f"First error (segment {first_segment}): {first_error}"
    )
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."
    return text
