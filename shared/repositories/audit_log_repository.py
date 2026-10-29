from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, audit_log: AuditLog) -> AuditLog:
        self._session.add(audit_log)
        await self._session.flush()
        return audit_log

    async def list(
        self,
        route_id: str | None = None,
        source: str | None = None,
        outcome: str | None = None,
        action_prefix: str | None = None,
        before_id: int | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Newest first. Use ``before_id`` (the last id of the previous page) to page back in time."""
        stmt = select(AuditLog)
        if route_id is not None:
            stmt = stmt.where(AuditLog.route_id == route_id)
        if source is not None:
            stmt = stmt.where(AuditLog.source == source)
        if outcome is not None:
            stmt = stmt.where(AuditLog.outcome == outcome)
        if action_prefix is not None:
            stmt = stmt.where(AuditLog.action.startswith(action_prefix))
        if before_id is not None:
            stmt = stmt.where(AuditLog.id < before_id)
        stmt = stmt.order_by(AuditLog.id.desc()).limit(limit)
        result = await self._session.scalars(stmt)
        return list(result.all())
