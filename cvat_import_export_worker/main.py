import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import signal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.enums import JobSegmentRunImportStatus
from db.models.job_segment_run_import import JobSegmentRunImport
from db.url import build_database_url
from repositories.artifact_repository import ArtifactRepository
from repositories.frame_artifact_repository import FrameArtifactRepository
from repositories.frame_repository import FrameRepository
from repositories.job_segment_run_repository import JobSegmentRunRepository
from repositories.job_segment_run_import_repository import JobSegmentRunImportRepository
from repositories.segment_repository import SegmentRepository
from services.artifact_service import ArtifactService
from services.cvat_service import CVATService
from services.errors import JobSegmentRunNotFoundError
from services.frame_artifact_downloader_service import FrameArtifactDownloaderService
from services.frame_artifact_service import FrameArtifactService
from services.frame_service import FrameService
from services.job_segment_artifiact_downloader_service import JobSegmentArtifactDownloaderService
from services.job_segment_run_import_service import JobSegmentRunImportService
from services.job_segment_run_service import JobSegmentRunService
from services.minio_service import MinioService
from services.segment_artifact_download_service import SegmentArtifactDownloadService
from services.segment_service import SegmentService
from utilities.cvat_utilities import get_task_url
from services.audit_service import (
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    configure_audit,
    entity_id_for,
    record_audit,
)
from utilities.error_utilities import describe_exception, error_code_of, record_failure
from utilities.logging_utilities import configure_logging


POLL_INTERVAL_SECONDS = 1.0
DATA_DIR = Path("/app/cvat_share")

logger = configure_logging("cvat_import_export_worker")

STALE_IMPORT_ERROR = (
    "The cvat_import_export_worker restarted while this was {action}, so it was stopped. "
    "| How to fix: Try the CVAT action again from the segment page."
)


def _import_ids(job_segment_run_import: JobSegmentRunImport) -> dict:
    """Plain IDs of an import, safe to use after a session rollback."""
    return dict(
        job_run_num=job_segment_run_import.job_run_num,
        job_def_id=job_segment_run_import.job_def_id,
        route_id=job_segment_run_import.route_id,
        segment_id=job_segment_run_import.segment_id,
        camera=job_segment_run_import.camera,
    )


async def _audit_import(action: str, outcome: str, ids: dict, message: str | None = None, error_code: str | None = None, details: dict | None = None) -> None:
    await record_audit(
        action,
        outcome,
        entity_type="cvat_import",
        entity_id=entity_id_for("cvat_import", ids),
        route_id=ids["route_id"],
        message=message,
        error_code=error_code,
        details={**{k: str(v) for k, v in ids.items()}, **(details or {})},
    )


def _import_label(ids: dict) -> str:
    return (
        f"cvat_import(route={ids['route_id']} segment={ids['segment_id']} "
        f"job_def={ids['job_def_id']} run={ids['job_run_num']} camera={ids['camera']})"
    )

async def _mark_stale_running_jobs_as_failed(job_segment_run_import_service: JobSegmentRunImportService):
    logger.info("Marking stale running jobs as failed")
    for status, action in (
        (JobSegmentRunImportStatus.LOADING, "loading into CVAT"),
        (JobSegmentRunImportStatus.REMOVING, "being removed from CVAT"),
    ):
        stale_jobs = await job_segment_run_import_service.get_by_status(status=status)
        for job in stale_jobs:
            logger.warning("Stale %s (status %s) marked as FAILED", _import_label(_import_ids(job)), status)
            await job_segment_run_import_service.set_error(
                job_segment_run_import=job,
                error_message=STALE_IMPORT_ERROR.format(action=action),
            )
            await _audit_import(
                "cvat.import.interrupted", OUTCOME_FAILURE, _import_ids(job),
                message=STALE_IMPORT_ERROR.format(action=action),
            )

    logger.info("Completed marking stale running jobs as failed.")


async def _process_loading_job(
    job_segment_run_import:JobSegmentRunImport,
    job_segment_run_import_service:JobSegmentRunImportService,
    cvat_service:CVATService,
    job_segment_run_service: JobSegmentRunService,
    job_segment_artifact_downloader_service: JobSegmentArtifactDownloaderService,
    session: AsyncSession
):
    ids = _import_ids(job_segment_run_import)
    label = _import_label(ids)
    logger.info("Loading into CVAT: %s", label)

    unique_folder_name = str(uuid4())
    dest_path = DATA_DIR / unique_folder_name
    try:
        await job_segment_run_import_service.set_status(**ids, status=JobSegmentRunImportStatus.LOADING)
        await session.commit()

        # Download job run info from minio
        job_segment_run = await job_segment_run_service.get_job_segment_run(
            job_run_num=job_segment_run_import.job_run_num,
            job_def_id=job_segment_run_import.job_def_id,
            route_id=job_segment_run_import.route_id,
            segment_id=job_segment_run_import.segment_id,
            camera=job_segment_run_import.camera,
        )
        if not job_segment_run:
            raise JobSegmentRunNotFoundError(
                job_run_num=job_segment_run_import.job_run_num,
                job_def_id=job_segment_run_import.job_def_id,
                route_id=job_segment_run_import.route_id,
                segment_id=job_segment_run_import.segment_id,
            )

        job_segment_run_dir = await job_segment_artifact_downloader_service.download_job_segment_run_artifacts(
            job_segment_run=job_segment_run,
            dest_path=dest_path
        )

        # Create task in cvat
        task_name = f"{job_segment_run_import.route_id}-{job_segment_run_import.segment_id}-{job_segment_run_import.job_def_id}-{job_segment_run_import.job_run_num}-export"
        new_task = cvat_service.create_new_annotated_task_for_job_segment_run_dir(
            job_segment_run_dir=job_segment_run_dir,
            task_name=task_name
        )

        task_id = new_task.id
        job_id = new_task.get_jobs()[0].id

        job_segment_run_import.task_url = get_task_url(task_id=task_id, job_id=job_id)
        job_segment_run_import.task_id = task_id


        await job_segment_run_import_service.set_status(
            job_run_num=job_segment_run_import.job_run_num,
            job_def_id=job_segment_run_import.job_def_id,
            route_id=job_segment_run_import.route_id,
            segment_id=job_segment_run_import.segment_id,
            camera=job_segment_run_import.camera,
            status=JobSegmentRunImportStatus.LOADED
        )
        await session.commit()
        logger.info("Loaded into CVAT: %s (task %s)", label, task_id)
        await _audit_import("cvat.load_segment.finished", OUTCOME_SUCCESS, ids, details={"task_id": task_id})
    except Exception as e:
        error = f"Failed while loading into CVAT: {describe_exception(e)}"
        logger.exception("Loading into CVAT failed: %s", label)
        await record_failure(
            session,
            logger,
            label,
            lambda: job_segment_run_import_service.mark_failed(**ids, error_message=error),
        )
        await _audit_import("cvat.load_segment.finished", OUTCOME_FAILURE, ids, message=error, error_code=error_code_of(e))
    finally:
        # The folder may not exist if the failure happened before the download
        shutil.rmtree(dest_path, ignore_errors=True)

async def _process_removal_job(
    job_segment_run_import:JobSegmentRunImport,
    job_segment_run_import_service:JobSegmentRunImportService,
    cvat_service:CVATService,
    session: AsyncSession
):
    ids = _import_ids(job_segment_run_import)
    label = _import_label(ids)
    logger.info("Removing from CVAT: %s", label)

    try:
        await job_segment_run_import_service.set_status(**ids, status=JobSegmentRunImportStatus.REMOVING)
        await session.commit()

        # Try to remove job from CVAT
        if not job_segment_run_import.task_id:
            raise ValueError(f"{label} has no CVAT task id, so there is nothing to remove")

        cvat_service.delete_task(
            task_id=job_segment_run_import.task_id
        )

        await job_segment_run_import_service.set_status(
            job_run_num=job_segment_run_import.job_run_num,
            job_def_id=job_segment_run_import.job_def_id,
            route_id=job_segment_run_import.route_id,
            segment_id=job_segment_run_import.segment_id,
            camera=job_segment_run_import.camera,
            status=JobSegmentRunImportStatus.REMOVED
        )
        await session.commit()
        logger.info("Removed from CVAT: %s", label)
        await _audit_import("cvat.remove_segment.finished", OUTCOME_SUCCESS, ids)
    except Exception as e:
        error = f"Failed while removing from CVAT: {describe_exception(e)}"
        logger.exception("Removing from CVAT failed: %s", label)
        await record_failure(
            session,
            logger,
            label,
            lambda: job_segment_run_import_service.mark_failed(**ids, error_message=error),
        )
        await _audit_import("cvat.remove_segment.finished", OUTCOME_FAILURE, ids, message=error, error_code=error_code_of(e))

async def _process_job(
    job_segment_run_import:JobSegmentRunImport,
    job_segment_run_import_service:JobSegmentRunImportService,
    job_segment_run_service:JobSegmentRunService,
    job_segment_artifact_downloader_service: JobSegmentArtifactDownloaderService,
    cvat_service:CVATService,
    session: AsyncSession
):
    logger.info("Processing %s", _import_label(_import_ids(job_segment_run_import)))
    if job_segment_run_import.status == JobSegmentRunImportStatus.QUEUED_FOR_LOADING:
        await _process_loading_job(
            job_segment_run_import=job_segment_run_import,
            job_segment_run_import_service=job_segment_run_import_service,
            job_segment_run_service=job_segment_run_service,
            job_segment_artifact_downloader_service=job_segment_artifact_downloader_service,
            cvat_service=cvat_service,
            session=session
        )
    elif job_segment_run_import.status == JobSegmentRunImportStatus.QUEUED_FOR_REMOVAL:
        await _process_removal_job(
            job_segment_run_import=job_segment_run_import,
            job_segment_run_import_service=job_segment_run_import_service,
            cvat_service=cvat_service,
            session=session
        )
    else:
        raise ValueError(f"Invalid status on {job_segment_run_import}")

async def main():
    logger.info("Starting worker")
    
    engine = create_async_engine(
        url=build_database_url(),
        pool_pre_ping=True
    )
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    configure_audit(SessionLocal, source="cvat_import_export_worker")

    stop_event = asyncio.Event()
    executor = ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig=sig, callback=stop_event.set)

    try:
        async with SessionLocal() as session:
            job_segment_run_import_repository = JobSegmentRunImportRepository(session=session)
            job_segment_run_import_service = JobSegmentRunImportService(job_segment_run_import_repository)
            frame_repository = FrameRepository(session=session)
            frame_service = FrameService(frame_repository)
            artifact_repository = ArtifactRepository(session=session)
            artifact_service = ArtifactService(artifact_repository)
            cvat_service = CVATService()
            job_segment_run_repository = JobSegmentRunRepository(session=session)
            job_segment_run_service = JobSegmentRunService(job_segment_run_repository)
            minio_service = MinioService()
            segment_repository = SegmentRepository(session)
            segment_service = SegmentService(segment_repository)
            frame_artifact_repository = FrameArtifactRepository(session=session)
            frame_artifact_service = FrameArtifactService(frame_artifact_repository)
            frame_artifact_downloader_service = FrameArtifactDownloaderService(
                frame_service=frame_service,
                frame_artifact_service=frame_artifact_service,
                artifact_service=artifact_service,
                minio_service=minio_service
            )
            segment_artifact_download_service = SegmentArtifactDownloadService(
                frame_service=frame_service,
                frame_artifact_downloader_service=frame_artifact_downloader_service
            )
            job_segment_artifact_downloader_service = JobSegmentArtifactDownloaderService(
                job_segment_run_service=job_segment_run_service,
                artifact_service=artifact_service,
                segment_artifact_download_service=segment_artifact_download_service,
                segment_service=segment_service,
                minio_service=minio_service
            )



            await _mark_stale_running_jobs_as_failed(
                job_segment_run_import_service=job_segment_run_import_service
            )
            await session.commit()

            while not stop_event.is_set():
                logger.debug("Checking for queued job segment run imports")
                job_segment_run_import = await job_segment_run_import_service.get_next_by_statuses(statuses=[JobSegmentRunImportStatus.QUEUED_FOR_LOADING, JobSegmentRunImportStatus.QUEUED_FOR_REMOVAL])

                if job_segment_run_import is None:
                    await session.rollback()
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                await _process_job(
                    job_segment_run_import=job_segment_run_import,
                    job_segment_run_import_service=job_segment_run_import_service,
                    job_segment_run_service=job_segment_run_service,
                    job_segment_artifact_downloader_service=job_segment_artifact_downloader_service,
                    cvat_service=cvat_service,
                    session=session,
                )






    finally:
        executor.shutdown(wait=False)
        await engine.dispose()
        logger.info("Worker Shutdown Complete")


if __name__ == "__main__":
    asyncio.run(main())
