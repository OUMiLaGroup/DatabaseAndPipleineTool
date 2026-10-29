import logging
from pathlib import Path

from db.enums import JobSegmentRunStatus, ArtifactKind
from db.models.job_segment_run import JobSegmentRun
from models.job_segment_run_dir import JobSegmentRunDir
from services.artifact_service import ArtifactService
from services.errors import SegmentNotFoundError
from services.job_segment_run_service import JobSegmentRunService
from services.minio_service import MinioService
from services.segment_artifact_download_service import SegmentArtifactDownloadService
from services.segment_service import SegmentService

logger = logging.getLogger(__name__)

class JobSegmentArtifactDownloaderService:
    """
    Service for downloading job segment artifacts
    """

    def __init__(
        self,
        job_segment_run_service: JobSegmentRunService,
        artifact_service: ArtifactService,
        segment_artifact_download_service: SegmentArtifactDownloadService,
        segment_service: SegmentService,
        minio_service: MinioService
    ):
        self._job_segment_run_service = job_segment_run_service
        self._artifact_service = artifact_service
        self._segment_artifact_download_service = segment_artifact_download_service
        self._segment_service = segment_service
        self._minio_service = minio_service

    async def download_annotations(
        self,
        job_segment_run: JobSegmentRun,
        dest_path: Path
    ) -> None:
        if job_segment_run.artifact_id is None:
            raise ValueError(f"{job_segment_run} does not have an artifact_id")

        artifact = await self._artifact_service.get_artifact(
            artifact_id=job_segment_run.artifact_id
        )

        if not artifact:
            raise ValueError(f"No artifact found with artifact_id {job_segment_run.artifact_id}")
        if artifact.kind == ArtifactKind.ZIP:
            raise ValueError("Pixel depth maps cannot be imported as CVAT COCO boxes. Use Export to download the depth labels and matching images.")

        self._minio_service.download_artifact(
            artifact=artifact,
            dest_path=dest_path
        )

    async def download_job_segment_run_artifacts(
        self,
        job_segment_run: JobSegmentRun,
        dest_path: Path
    ) -> JobSegmentRunDir:
        """
        Download the images and annotations for a job segment run and store them in a folder.
        """
        logging.info(f"Downloading jobb segment run artifacts for {job_segment_run}")
        if not job_segment_run.status == JobSegmentRunStatus.SUCCEEDED:
            raise ValueError(f"Can not download job segment run artifacts for {job_segment_run} because status is not SUCCEEDED")

        segment = await self._segment_service.get_segment(
            route_id=job_segment_run.route_id,
            segment_id=job_segment_run.segment_id
        )

        if not segment:
            raise SegmentNotFoundError(
                route_id=job_segment_run.route_id,
                segment_id=job_segment_run.segment_id
            )

        image_paths = await self._segment_artifact_download_service.download_segment_frames(
            segment=segment,
            dest_path=dest_path,
            camera=job_segment_run.camera,
        )

        annotations_path = dest_path / "annotations.json"
        await self.download_annotations(
            job_segment_run=job_segment_run,
            dest_path=annotations_path
        )

        return JobSegmentRunDir(
            image_paths=image_paths,
            annotation_path=annotations_path
        )
