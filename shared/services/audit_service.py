"""
Audit log: a permanent record of what happened in the pipeline.

* The API records every change request (create/delete/cancel/requeue/...) with its outcome,
  including failed attempts and the error code the user saw (see backend/api/audit.py).
* Workers record the outcome of their work (route downloads/uploads, job runs, CVAT imports,
  dataset exports) through ``record_audit`` below.

Writing to the audit log is best-effort: it uses its own database session, so it is not lost
when the action's own transaction is rolled back, and a failure to write it is logged but never
breaks the action being audited.

Workers set it up once at startup:

    configure_audit(SessionLocal, source="cvat_worker")

and then call:

    await record_audit("job_run.completed", outcome="success", entity_type="job_run", ...)
"""
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.audit_log import AuditLog
from repositories.audit_log_repository import AuditLogRepository

logger = logging.getLogger(__name__)

OUTCOME_SUCCESS = "success"
OUTCOME_WARNING = "warning"
OUTCOME_FAILURE = "failure"
OUTCOMES = (OUTCOME_SUCCESS, OUTCOME_WARNING, OUTCOME_FAILURE)

_MAX_MESSAGE_LENGTH = 1000


class AuditService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], source: str) -> None:
        self._session_factory = session_factory
        self._source = source

    async def record(
        self,
        action: str,
        outcome: str,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        route_id: str | None = None,
        message: str | None = None,
        error_code: str | None = None,
        request_id: str | None = None,
        details: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> None:
        """Write one audit row in its own transaction. Never raises."""
        if outcome not in OUTCOMES:
            outcome = OUTCOME_FAILURE if outcome in ("failed", "error") else OUTCOME_SUCCESS
        if message and len(message) > _MAX_MESSAGE_LENGTH:
            message = message[: _MAX_MESSAGE_LENGTH - 3] + "..."
        try:
            async with self._session_factory() as session:
                await AuditLogRepository(session).add(
                    AuditLog(
                        source=source or self._source,
                        action=action,
                        outcome=outcome,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        route_id=route_id,
                        message=message,
                        error_code=error_code,
                        request_id=request_id,
                        details=details,
                    )
                )
                await session.commit()
        except Exception:
            logger.exception("Could not write audit log entry action=%s entity=%s", action, entity_id)


def entity_id_for(entity_type: str | None, ids: dict[str, Any]) -> str | None:
    """Readable ID for the thing acted on, e.g. "db47...|0000...--9ecd/def 2/run 5/front_wide"."""
    def part(key: str, label: str = "") -> str | None:
        value = ids.get(key)
        return None if value is None else f"{label}{value}"

    if entity_type == "route":
        parts = [part("route_id")]
    elif entity_type == "job_definition":
        parts = [part("job_def_id", "def ")]
    elif entity_type == "job_run":
        parts = [part("route_id"), part("job_def_id", "def "), part("job_run_num", "run "), part("camera")]
    elif entity_type == "cvat_import":
        parts = [part("route_id"), part("segment_id", "seg "), part("job_def_id", "def "), part("job_run_num", "run "), part("camera")]
    elif entity_type == "dataset_export":
        parts = [part("export_id"), part("route_id")]
    else:
        parts = []
    present = [p for p in parts if p]
    return "/".join(present) if present else None



# ─── Process-wide instance for workers ────────────────────────────────────────

_audit_service: AuditService | None = None


def configure_audit(session_factory: async_sessionmaker[AsyncSession], source: str) -> AuditService:
    """Call once at worker startup. Until then ``record_audit`` does nothing (e.g. in unit tests)."""
    global _audit_service
    _audit_service = AuditService(session_factory, source)
    return _audit_service


async def record_audit(action: str, outcome: str, **kwargs: Any) -> None:
    if _audit_service is None:
        return
    await _audit_service.record(action, outcome, **kwargs)
