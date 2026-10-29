from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import CameraType
from db.models.job_run import JobRun, JobStatus
from db.models.job_segment_run import JobSegmentRun


class JobRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_segments_for_export(self, job_run_num: int, job_def_id: int, route_id: str, camera: CameraType) -> list[JobSegmentRun]:
        return list((await self._session.scalars(select(JobSegmentRun).where(
            JobSegmentRun.job_run_num == job_run_num, JobSegmentRun.job_def_id == job_def_id,
            JobSegmentRun.route_id == route_id, JobSegmentRun.camera == camera,
        ))).all())

    async def get_by_id(self, job_run_num:int, job_def_id:int, route_id:str, camera: CameraType) -> JobRun | None:
        return await self._session.get(JobRun, {
            "job_run_num":job_run_num, 
            "job_def_id": job_def_id, 
            "route_id": route_id,
            "camera": camera,
        }) # id refer to job_run_id in JobRun model

    async def list_all(self) -> list[JobRun]:
        stmt = select(JobRun).order_by(JobRun.queued_at.desc()) # order by queued_at in descending order to get the most recent job runs first
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_by_route_id(self, route_id: str) -> list[JobRun]:
        stmt = select(JobRun).where(JobRun.route_id == route_id).order_by(JobRun.queued_at.desc())
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_by_status(self, status: JobStatus) -> list[JobRun]:
        stmt = (
            select(JobRun)
            .where(JobRun.status == status)
            .order_by(JobRun.queued_at.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def get_next_by_status(self, status: JobStatus) -> JobRun | None:
        stmt = (
            select(JobRun)
            .where(JobRun.status == status)
            .order_by(JobRun.queued_at.asc())
            .limit(1) # for now just get next job run at for simple stuff
        )
        result = await self._session.scalars(stmt)
        return result.first()

    async def claim_next_queued(self, started_at: datetime) -> JobRun | None:
        next_job_stmt = (
            select(
                JobRun.job_run_num,
                JobRun.job_def_id,
                JobRun.route_id,
                JobRun.camera,
            )
            .where(JobRun.status == JobStatus.QUEUED)
            .order_by(JobRun.queued_at.asc())
            .limit(1)
            .subquery()
        )
        stmt = (
            update(JobRun)
            .where(
                JobRun.job_run_num == next_job_stmt.c.job_run_num,
                JobRun.job_def_id == next_job_stmt.c.job_def_id,
                JobRun.route_id == next_job_stmt.c.route_id,
                JobRun.camera == next_job_stmt.c.camera,
                JobRun.status == JobStatus.QUEUED,
            )
            .values(status=JobStatus.RUNNING, started_at=started_at)
            .returning(JobRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def transition_status(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
        current_status: JobStatus,
        new_status: JobStatus,
        *,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> JobRun | None:
        values: dict[str, object] = {"status": new_status}
        if started_at is not None:
            values["started_at"] = started_at
        if finished_at is not None:
            values["finished_at"] = finished_at

        stmt = (
            update(JobRun)
            .where(
                JobRun.job_run_num == job_run_num,
                JobRun.job_def_id == job_def_id,
                JobRun.route_id == route_id,
                JobRun.camera == camera,
                JobRun.status == current_status,
            )
            .values(**values)
            .returning(JobRun)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
    ) -> JobRun:
        job_run = JobRun(
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera,
            status=JobStatus.QUEUED,
        )
        self._session.add(job_run)
        await self._session.flush()
        return job_run

    async def save(self, job_run: JobRun) -> JobRun:
        self._session.add(job_run)
        await self._session.flush()
        return job_run

    async def delete(self, job_run: JobRun) -> None:
        await self._session.delete(job_run)
        await self._session.flush()
