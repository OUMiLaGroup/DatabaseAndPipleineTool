import logging
from datetime import datetime, timezone
from uuid import UUID

from db.enums import CameraType, DatasetExportStatus, JobStatus, RouteStatus, JobSegmentRunStatus
from db.models.artifact import Artifact
from db.models.dataset_export import DatasetExport
from db.models.dataset_export_job_run import DatasetExportJobRun
from repositories.artifact_repository import ArtifactRepository
from repositories.dataset_export_job_run_repository import DatasetExportJobRunRepository
from repositories.dataset_export_repository import DatasetExportRepository
from repositories.job_run_repository import JobRunRepository
from repositories.route_repository import RouteRepository
from services.frame_service import FrameService
from services.minio_service import MinioService
from services.errors import (
    ArtifactNotFoundError,
    DatasetExportDeletionConflictError,
    DatasetExportNotFoundError,
    DatasetExportValidationError,
    JobRunNotFoundError,
    RouteNotFoundError,
)

logger = logging.getLogger(__name__)


class DatasetExportService:
    def __init__(
        self,
        dataset_export_repository: DatasetExportRepository,
        dataset_export_job_run_repository: DatasetExportJobRunRepository,
        route_repository: RouteRepository,
        job_run_repository: JobRunRepository,
        frame_service: FrameService,
        artifact_repository: ArtifactRepository,
    ) -> None:
        self._dataset_export_repository = dataset_export_repository
        self._dataset_export_job_run_repository = dataset_export_job_run_repository
        self._route_repository = route_repository
        self._job_run_repository = job_run_repository
        self._frame_service = frame_service
        self._artifact_repository = artifact_repository

    async def list_dataset_exports(self) -> list[DatasetExport]:
        logger.info("Listing all dataset exports")
        return await self._dataset_export_repository.list_all()

    async def get_dataset_exports_by_route_id(self, route_id: str) -> list[DatasetExport]:
        logger.info("Listing dataset exports for route_id=%s", route_id)
        return await self._dataset_export_repository.get_by_route_id(route_id)

    async def get_dataset_exports_by_status(
        self,
        status: DatasetExportStatus,
    ) -> list[DatasetExport]:
        logger.info("Listing dataset exports for status=%s", status)
        return await self._dataset_export_repository.get_by_status(status)

    async def get_dataset_export(self, export_id: int) -> DatasetExport | None:
        logger.info("Getting dataset export export_id=%s", export_id)
        return await self._dataset_export_repository.get_by_id(export_id)

    async def get_next_dataset_export_by_status(
        self,
        status: DatasetExportStatus,
    ) -> DatasetExport | None:
        logger.info("Getting next dataset export with status=%s", status)
        return await self._dataset_export_repository.get_next_by_status(status)

    async def get_selected_job_runs(self, export_id: int) -> list[DatasetExportJobRun]:
        logger.info("Getting selected job runs for export_id=%s", export_id)
        return await self._dataset_export_job_run_repository.list_by_export_id(export_id)

    async def create_dataset_export(
        self,
        route_id: str,
        camera_views: list[CameraType],
        job_runs: list[tuple[int, int, CameraType]],
    ) -> DatasetExport:
        logger.info(
            "Creating dataset export route_id=%s camera_views=%s job_runs=%s",
            route_id,
            [camera_view.value for camera_view in camera_views],
            [(job_def_id, job_run_num, camera.value) for job_def_id, job_run_num, camera in job_runs],
        )
        route = await self._route_repository.get_by_id(route_id)
        if route is None:
            raise RouteNotFoundError(route_id)

        if route.status != RouteStatus.UPLOADED:
            raise DatasetExportValidationError(
                f"Route {route_id} must be UPLOADED before export creation"
            )

        if not camera_views:
            raise DatasetExportValidationError("camera_views must contain at least one camera")

        unique_camera_views = {camera_view.value for camera_view in camera_views}
        if len(unique_camera_views) != len(camera_views):
            raise DatasetExportValidationError("camera_views must not contain duplicates")
        await self._validate_camera_views_exist_on_route(
            route_id=route_id,
            camera_views=camera_views,
        )

        unique_job_runs = set(job_runs)
        if len(unique_job_runs) != len(job_runs):
            raise DatasetExportValidationError("job_runs must not contain duplicates")

        validated_job_runs: list[tuple[int, int, CameraType]] = []
        for job_def_id, job_run_num, camera in job_runs:
            job_run = await self._job_run_repository.get_by_id(
                job_run_num=job_run_num,
                job_def_id=job_def_id,
                route_id=route_id,
                camera=camera,
            )
            if job_run is None:
                raise JobRunNotFoundError(
                    job_run_num=job_run_num,
                    job_def_id=job_def_id,
                    route_id=route_id,
                )
            if job_run.status != JobStatus.SUCCEEDED:
                raise DatasetExportValidationError(
                    "All referenced job runs must be SUCCEEDED before export creation"
                )
            validated_job_runs.append((job_def_id, job_run_num, camera))
            segments = await self._job_run_repository.get_segments_for_export(job_run_num, job_def_id, route_id, camera)
            incomplete = [s.segment_id for s in segments if s.status != JobSegmentRunStatus.SUCCEEDED or s.artifact_id is None]
            if not segments or incomplete:
                raise DatasetExportValidationError(f"Cannot export job {job_def_id}, run {job_run_num}: annotation outputs are missing or incomplete for segments {incomplete}. Repair the annotation job first.")

        dataset_export = await self._dataset_export_repository.create(
            route_id=route_id,
            camera_views=[camera_view.value for camera_view in camera_views],
            status=DatasetExportStatus.QUEUED,
        )

        for job_def_id, job_run_num, camera in validated_job_runs:
            await self._dataset_export_job_run_repository.create(
                export_id=dataset_export.export_id,
                route_id=route_id,
                job_def_id=job_def_id,
                job_run_num=job_run_num,
                camera=camera,
            )

        logger.info("Created dataset export export_id=%s", dataset_export.export_id)
        return dataset_export

    async def set_status(
        self,
        export_id: int,
        status: DatasetExportStatus,
    ) -> DatasetExport:
        logger.info("Setting dataset export status export_id=%s status=%s", export_id, status)
        dataset_export = await self._require_dataset_export(export_id)
        dataset_export.status = status
        if status == DatasetExportStatus.RUNNING:
            dataset_export.started_at = datetime.now(timezone.utc)
        if status in (DatasetExportStatus.SUCCEEDED, DatasetExportStatus.FAILED):
            dataset_export.finished_at = datetime.now(timezone.utc)
        return await self._dataset_export_repository.save(dataset_export)

    async def set_error(self, export_id: int, error: str | None) -> DatasetExport:
        logger.info("Setting dataset export error export_id=%s error=%s", export_id, error)
        dataset_export = await self._require_dataset_export(export_id)
        dataset_export.error = error
        dataset_export.status = DatasetExportStatus.FAILED
        dataset_export.finished_at = datetime.now(timezone.utc)
        return await self._dataset_export_repository.save(dataset_export)

    async def set_zip_artifact(
        self,
        export_id: int,
        artifact_id: UUID,
    ) -> DatasetExport:
        logger.info(
            "Setting dataset export zip artifact export_id=%s artifact_id=%s",
            export_id,
            artifact_id,
        )
        dataset_export = await self._require_dataset_export(export_id)
        dataset_export.zip_artifact_id = artifact_id
        return await self._dataset_export_repository.save(dataset_export)

    async def get_download_artifact(
        self,
        export_id: int,
    ) -> tuple[DatasetExport, Artifact]:
        logger.info("Getting dataset export download artifact export_id=%s", export_id)
        dataset_export = await self._require_dataset_export(export_id)
        if dataset_export.status != DatasetExportStatus.SUCCEEDED:
            raise DatasetExportValidationError(
                f"Dataset export {export_id} is not ready for download"
            )
        if dataset_export.zip_artifact_id is None:
            raise DatasetExportValidationError(
                f"Dataset export {export_id} is not ready for download"
            )

        artifact = await self._artifact_repository.get_by_id(dataset_export.zip_artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(dataset_export.zip_artifact_id)

        return dataset_export, artifact

    async def delete_dataset_export(self, export_id: int) -> None:
        logger.info("Deleting dataset export export_id=%s", export_id)
        dataset_export = await self._require_dataset_export(export_id)
        if dataset_export.status == DatasetExportStatus.RUNNING:
            raise DatasetExportDeletionConflictError(export_id)
        artifact: Artifact | None = None
        if dataset_export.zip_artifact_id is not None:
            artifact = await self._artifact_repository.get_by_id(dataset_export.zip_artifact_id)
            if artifact is None:
                raise ArtifactNotFoundError(dataset_export.zip_artifact_id)
            minio_service = MinioService()
            minio_service.delete_object(
                bucket_name=artifact.bucket,
                object_key=artifact.object_key,
            )
        await self._dataset_export_repository.delete(dataset_export)
        if artifact is not None:
            await self._artifact_repository.delete(artifact)

    async def _require_dataset_export(self, export_id: int) -> DatasetExport:
        dataset_export = await self._dataset_export_repository.get_by_id(export_id)
        if dataset_export is None:
            raise DatasetExportNotFoundError(export_id)
        return dataset_export

    async def _validate_camera_views_exist_on_route(
        self,
        route_id: str,
        camera_views: list[CameraType],
    ) -> None:
        for camera_view in camera_views:
            logger.info(
                "Validating camera view exists on route route_id=%s camera=%s",
                route_id,
                camera_view.value,
            )
            camera_exists = await self._frame_service.camera_exists_on_route(
                route_id=route_id,
                camera=camera_view,
            )
            if not camera_exists:
                raise DatasetExportValidationError(
                    f"Requested camera view {camera_view.value} has no frames for route {route_id}"
                )
