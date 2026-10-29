from uuid import UUID

from sqlalchemy import ForeignKeyConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.enums import CameraType, JobSegmentRunStatus, job_segment_run_enum, camera_type_enum


class JobSegmentRun(Base):
    __tablename__ = "job_segment_run"

    __table_args__ = (
        ForeignKeyConstraint(
            ["job_run_num", "route_id", "job_def_id", "camera"],
            ["job_runs.job_run_num", "job_runs.route_id", "job_runs.job_def_id", "job_runs.camera"],
            ondelete="CASCADE",
        ),
    )

    # primary keys
    job_run_num: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    route_id: Mapped[str] = mapped_column(
        primary_key=True,
    )

    job_def_id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    camera: Mapped[CameraType] = mapped_column(
        camera_type_enum,
        primary_key=True
    )

    segment_id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    # segment info
    status: Mapped[JobSegmentRunStatus] = mapped_column(
        job_segment_run_enum,
        nullable=False,
    )

    artifact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("artifacts.artifact_id"), 
        nullable=True
    )

    # Why this segment of the job run failed (or a warning, e.g. some segments failed). Shown in the UI.
    error: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    def __repr__(self):
        return f"JobSegmentRun({self.job_run_num=}, {self.route_id=}, {self.job_def_id=}, {self.segment_id=}, {self.status=})"
