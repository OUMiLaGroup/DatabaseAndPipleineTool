import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_session
from repositories.audit_log_repository import AuditLogRepository
from schemas.audit_log import AuditLogResponse
from services.audit_service import OUTCOMES
from services.errors import InvalidAuditFilterError

logger = logging.getLogger(__name__)

audit_logs_router = APIRouter(
    prefix="/audit-logs",
)


@audit_logs_router.get("/", response_model=list[AuditLogResponse])
async def list_audit_logs(
    route_id: str | None = None,
    source: str | None = Query(None, description='"api" or a worker name, e.g. "cvat_worker"'),
    outcome: str | None = Query(None, description="success, warning or failure"),
    action: str | None = Query(None, description='Action prefix, e.g. "job_run" or "route.import"'),
    before_id: int | None = Query(None, description="Return entries older than this id (for paging)"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
):
    """Audit log entries, newest first."""
    if outcome is not None and outcome not in OUTCOMES:
        raise InvalidAuditFilterError(f"Unknown outcome '{outcome}'")
    return await AuditLogRepository(session).list(
        route_id=route_id,
        source=source,
        outcome=outcome,
        action_prefix=action,
        before_id=before_id,
        limit=limit,
    )
