from datetime import datetime, timezone
from db.enums import CameraType
from db.models.job_run import JobRun, JobStatus
from db.models.route import RouteStatus
from repositories.job_definition_repository import JobDefinitionRepository
from repositories.job_run_repository import JobRunRepository
from repositories.route_repository import RouteRepository
from services.errors import (
    JobRunCancelError,
    JobDefinitionNotFoundError,
    JobRunNotFoundError,
    JobRunRequeueError,
    RouteNotFoundError,
    RouteNotReadyForJobRunError,
)

# This service is responsible for managing job runs.
class JobRunService:
    def __init__(
        self,
        job_run_repository: JobRunRepository,
        route_repository: RouteRepository,
        job_definition_repository: JobDefinitionRepository,
    ) -> None:
        self._job_run_repository = job_run_repository
        self._route_repository = route_repository
        self._job_definition_repository = job_definition_repository

    async def list_job_runs(self) -> list[JobRun]:
        return await self._job_run_repository.list_all()

    async def list_job_runs_by_route(self, route_id: str) -> list[JobRun]:
        return await self._job_run_repository.list_by_route_id(route_id)

    async def get_job_runs_by_status(self, status: JobStatus) -> list[JobRun]:
        return await self._job_run_repository.get_by_status(status)

    async def get_next_job_run_by_status(self, status: JobStatus) -> JobRun | None:
        return await self._job_run_repository.get_next_by_status(status)

    async def claim_next_queued_job(self) -> JobRun | None:
        return await self._job_run_repository.claim_next_queued(
            started_at=datetime.now(timezone.utc)
        )

    async def get_job_run(self, job_run_num: int, job_def_id: int, route_id: str, camera: CameraType) -> JobRun | None:
        return await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )

    async def create_job_run(
        self,
        job_def_id: int,
        route_id: str,
        camera: CameraType
    ) -> JobRun:
        route = await self._route_repository.get_by_id(route_id)
        if route is None:
            raise RouteNotFoundError(route_id)

        if route.status != RouteStatus.UPLOADED:
            raise RouteNotReadyForJobRunError(route_id=route_id, status=str(route.status))

        job_definition = await self._job_definition_repository.get_by_id(job_def_id)
        if job_definition is None:
            raise JobDefinitionNotFoundError(job_def_id)

        return await self._job_run_repository.create(
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )

    async def set_status(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
        status: JobStatus,
    ) -> JobRun:
        job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num, 
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id
            )
        # When the status of a job run is updated,
        #  we also want to update
        job_run.status = status
        # THIS IS NEEDED
        if status == JobStatus.RUNNING:
            job_run.started_at = datetime.now(timezone.utc) # Set started_at when the job run starts running
        # if the job run is either succeeded, failed, or cancelled
        if status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
            job_run.finished_at = datetime.now(timezone.utc)

        return await self._job_run_repository.save(job_run)

    async def set_error(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
        error: str | None, #error is a string that describes the error that may have during job exec.
    ) -> JobRun:
        job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id
            )

        job_run.error = error
        job_run.status = JobStatus.FAILED
        # A failed run is finished; without this the UI showed failed runs with no end time
        job_run.finished_at = datetime.now(timezone.utc)
        return await self._job_run_repository.save(job_run)

    async def set_warning(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
        warning: str | None,
    ) -> JobRun:
        """Store a message in ``error`` without changing the status.

        Used when a job run succeeded overall but some segments failed.
        """
        job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id
            )
        job_run.error = warning
        return await self._job_run_repository.save(job_run)

    async def set_stats(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
        stats: dict | None,
    ) -> JobRun:
        job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id
            )

        job_run.stats = stats
        return await self._job_run_repository.save(job_run)

    async def delete_job_run(
        self, 
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType
    ) -> None:
        job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id
            )

        await self._job_run_repository.delete(job_run)

    async def cancel_job_run(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
    ) -> JobRun:
        job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id
            )
        if job_run.status != JobStatus.QUEUED:
            raise JobRunCancelError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id,
                reason=f"status is {job_run.status}",
            )

        cancelled_job_run = await self._job_run_repository.transition_status(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera,
            current_status=JobStatus.QUEUED,
            new_status=JobStatus.CANCELLED,
            finished_at=datetime.now(timezone.utc),
        )
        if cancelled_job_run is not None:
            return cancelled_job_run

        current_job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if current_job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id
            )

        raise JobRunCancelError(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            reason=f"status is {current_job_run.status}",
        )

    async def requeue_job_run(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        camera: CameraType,
    ) -> JobRun:
        job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id
            )
        if job_run.status != JobStatus.CANCELLED:
            raise JobRunRequeueError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id,
                reason=f"status is {job_run.status}",
            )

        requeued_job_run = await self._job_run_repository.transition_status(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera,
            current_status=JobStatus.CANCELLED,
            new_status=JobStatus.QUEUED,
        )
        if requeued_job_run is not None:
            return requeued_job_run
        
        current_job_run = await self._job_run_repository.get_by_id(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            camera=camera
        )
        if current_job_run is None:
            raise JobRunNotFoundError(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id
            )

        raise JobRunRequeueError(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id,
            reason=f"status is {current_job_run.status}",
        )