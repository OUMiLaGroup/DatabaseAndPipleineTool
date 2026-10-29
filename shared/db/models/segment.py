from datetime import datetime

from sqlalchemy import CheckConstraint, Integer, DateTime, String, func, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.enums import SegmentStatus, segment_status_enum
# this role tell segment for which stage belong to, like downloading or uploading


class Segment(Base):
    __tablename__ = "segments"
# this check constraint is used to ensure segment_id is non-negative
#  it should start from 0
    __table_args__ = (
        CheckConstraint("segment_id >= 0", name="ck_segments_segment_id_non_negative"),
    )

    route_id: Mapped[str] = mapped_column(
        ForeignKey("routes.route_id", ondelete="CASCADE"),
        primary_key=True,
    )
    segment_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[SegmentStatus] = mapped_column(
        segment_status_enum,
        #nullable=False means every segment must have a status, it cannot be nulls
        nullable=False,
    )
    segment_meta: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # Why this segment failed (or a warning, e.g. some segments failed). Shown in the UI.
    error: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    def __repr__(self):
        return f"Segment({self.route_id}, {self.segment_id}, {self.status})"
