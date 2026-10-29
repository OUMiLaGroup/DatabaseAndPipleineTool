from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AuditLog(Base):
    """One row per notable action: who/what did something, to what, and whether it worked.

    Rows are written by the API (every change request, including failed ones) and by the
    workers (outcomes of downloads, uploads, job runs, CVAT imports and exports).
    There is deliberately no foreign key to routes, so the history survives deleting a route.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_route_id_id", "route_id", "id"),
    )

    # BIGSERIAL on Postgres; plain INTEGER on SQLite so tests can auto-number rows
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    # "api" or the worker name, e.g. "cvat_worker"
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    # Dotted action name, e.g. "route.import", "job_run.cancel", "job_run.completed"
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # "success", "warning" (partly succeeded) or "failure"
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    route_id: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    # Error code from services/errors.py when the action failed, e.g. "ROUTE_NOT_READY"
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self):
        return f"AuditLog({self.id}, {self.source}, {self.action}, {self.outcome}, {self.entity_id})"
