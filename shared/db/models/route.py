from datetime import datetime

from sqlalchemy import CheckConstraint, String, DateTime, func, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.enums import RouteStatus, route_status_enum



class Route(Base):
    __tablename__ = "routes"

    __table_args__ = (
        CheckConstraint("route_id <> ''", name="ck_routes_route_id_not_empty"),
    )
    route_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )
    file_path: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    num_segments_expected: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    status: Mapped[RouteStatus] = mapped_column(
        route_status_enum,
    )
    meta: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    # Why this route failed (or a warning, e.g. some segments failed). Shown in the UI.
    error: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    def __repr__(self):
        return f"Route({self.route_id}, {self.file_path}, {self.status})"

    @property
    def download_error(self) -> dict | None:
        return (self.meta or {}).get('download_error')
