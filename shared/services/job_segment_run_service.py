from uuid import UUID

from db.enums import CameraType, JobSegmentRunStatus
from db.models.job_segment_run import JobSegmentRun
from repositories.job_segment_run_repository import JobSegmentRunRepository
from services.errors import JobSegmentRunAlreadyExistsError, JobSegmentRunNotFoundError


class JobSegmentRunService:
    def __init__(self, job_segment_run_repository: JobSegmentRunRepository) -> None:
        self._job_segment_run_repository = job_segment_run_repository

    async def list_job_segment_runs(self) -> list[JobSegmentRun]:
        return await self._job_segment_run_repository.list_all()

    async def get_job_segment_run(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        segment_id: int,
        camera: CameraType,
    ) -> JobSegmentRun | None:
        return await self._job_segment_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            segment_id=segment_id,
            camera=camera,
        )

    async def get_segments_by_job_run(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
    ) -> list[JobSegmentRun]:
        return await self._job_segment_run_repository.get_segments_by_job_run(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera,
        )

    async def get_segments_by_status(self, status: JobSegmentRunStatus) -> list[JobSegmentRun]:
        return await self._job_segment_run_repository.get_by_status(status)

    async def get_job_segment_runs_by_route_and_segment(
        self,
        route_id: str,
        segment_id: int,
    ) -> list[JobSegmentRun]:
        return await self._job_segment_run_repository.get_by_route_and_segment(
            route_id=route_id,
            segment_id=segment_id,
        )

    async def get_job_segment_runs_by_route_id(
        self,
        route_id: str,
    ) -> list[JobSegmentRun]:
        return await self._job_segment_run_repository.get_by_route_id(
            route_id=route_id,
        )

    async def create_job_segment_run(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        segment_id: int,
        camera: CameraType,
    ) -> JobSegmentRun:
        existing = await self._job_segment_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            segment_id=segment_id,
            camera=camera,
        )
        if existing is not None:
            raise JobSegmentRunAlreadyExistsError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id,
                segment_id=segment_id,
            )
        return await self._job_segment_run_repository.create(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            segment_id=segment_id,
            camera=camera,
        )

    async def set_status(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        segment_id: int,
        camera: CameraType,
        status: JobSegmentRunStatus,
        error: str | None = None,
    ) -> JobSegmentRun:
        """Set the status. Pass ``error`` to record why this segment failed (only written when given)."""
        segment_run = await self._job_segment_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            segment_id=segment_id,
            camera=camera,
        )
        if segment_run is None:
            raise JobSegmentRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id,
                segment_id=segment_id,
            )
        segment_run.status = status
        if error is not None:
            segment_run.error = error
        return await self._job_segment_run_repository.save(segment_run)

    async def set_artifact(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        segment_id: int,
        camera: CameraType,
        artifact_id: UUID,
    ) -> JobSegmentRun:
        segment_run = await self._job_segment_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            segment_id=segment_id,
            camera=camera,
        )
        if segment_run is None:
            raise JobSegmentRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id,
                segment_id=segment_id,
            )
        segment_run.artifact_id = artifact_id
        return await self._job_segment_run_repository.save(segment_run)

    async def delete_job_segment_run(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        segment_id: int,
        camera: CameraType,
    ) -> None:
        segment_run = await self._job_segment_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            segment_id=segment_id,
            camera=camera,
        )
        if segment_run is None:
            raise JobSegmentRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id,
                segment_id=segment_id,
            )
        await self._job_segment_run_repository.delete(segment_run)
