import asyncio
import json
import signal
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from utilities.depth_archive import extract_depth_archive
from utilities.depth_label_links import link_depth_to_coco

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.enums import ArtifactKind, ArtifactRole, CameraType, DatasetExportStatus
from db.models.dataset_export import DatasetExport
from db.models.dataset_export_job_run import DatasetExportJobRun
from db.url import build_database_url
from services.artifact_service import ArtifactService
from services.dataset_export_service import DatasetExportService
from services.frame_artifact_service import FrameArtifactService
from services.frame_service import FrameService
from services.job_segment_run_service import JobSegmentRunService
from services.minio_service import MinioService
from services.segment_artifact_service import SegmentArtifactService
from services.segment_service import SegmentService
from services.audit_service import OUTCOME_FAILURE, OUTCOME_SUCCESS, configure_audit, record_audit
from utilities.error_utilities import describe_exception, error_code_of, record_failure
from utilities.logging_utilities import configure_logging
from utilities.service_builder_utilities import (
    build_artifact_service,
    build_dataset_export_service,
    build_frame_artifact_service,
    build_frame_service,
    build_job_segment_run_service,
    build_segment_artifact_service,
    build_segment_service,
)


POLL_INTERVAL_SECONDS = 2.0
DATA_DIR = Path("/app/data_exports")

logger = configure_logging("dataset_export_worker")


async def _mark_stale_running_exports_as_failed(
    dataset_export_service: DatasetExportService,
    session: AsyncSession,
) -> None:
    logger.info("Checking for stale dataset exports")
    stale_exports = await dataset_export_service.get_dataset_exports_by_status(
        status=DatasetExportStatus.RUNNING
    )
    if not stale_exports:
        logger.info("No stale dataset exports found")
        return

    for dataset_export in stale_exports:
        logger.warning(
            "Marking stale dataset export as failed export_id=%s",
            dataset_export.export_id,
        )
        await record_audit(
            "dataset_export.interrupted", OUTCOME_FAILURE,
            entity_type="dataset_export",
            entity_id=f"{dataset_export.export_id}/{dataset_export.route_id}",
            route_id=dataset_export.route_id,
            message="The dataset_export_worker restarted while this export was RUNNING.",
        )
        await dataset_export_service.set_error(
            export_id=dataset_export.export_id,
            error=(
                "The dataset_export_worker restarted while this export was RUNNING. "
                "| How to fix: Use Retry on the export to run it again."
            ),
        )

    await session.commit()


async def _download_route_images(
    route_id: str,
    camera_views: list[str],
    export_root: Path,
    segment_service: SegmentService,
    frame_service: FrameService,
    frame_artifact_service: FrameArtifactService,
    artifact_service: ArtifactService,
    minio_service: MinioService,
) -> None:
    logger.info(
        "Downloading route images route_id=%s camera_views=%s",
        route_id,
        camera_views,
    )
    segments = await segment_service.get_segments_by_route(route_id=route_id)

    for segment in segments:
        for camera_view_str in camera_views:
            camera_view = CameraType(camera_view_str)
            frames = await frame_service.get_frames_by_route_segment(
                route_id=route_id,
                segment_id=segment.segment_id,
                camera=camera_view,
            )
            if not frames:
                logger.info(
                    "Skipping segment with no frames for selected camera route_id=%s segment_id=%s camera=%s",
                    route_id,
                    segment.segment_id,
                    camera_view.value,
                )
                continue

            camera_dir = (
                export_root
                / "segments"
                / str(segment.segment_id)
                / "images"
                / camera_view.value
            )
            camera_dir.mkdir(parents=True, exist_ok=True)

            for frame in frames:
                frame_artifact = await frame_artifact_service.get_frame_artifact(
                    frame_pk=frame.frame_pk,
                    role=ArtifactRole.FRAME_IMAGE,
                )
                if frame_artifact is None:
                    raise ValueError(f"Missing frame artifact for frame_pk={frame.frame_pk}")

                artifact = await artifact_service.get_artifact(
                    artifact_id=frame_artifact.artifact_id
                )
                if artifact is None:
                    raise ValueError(
                        f"Missing artifact for frame artifact id={frame_artifact.artifact_id}"
                    )

                image_path = camera_dir / f"{frame.frame_id}.png"
                minio_service.download_artifact(artifact=artifact, dest_path=image_path)


async def _download_route_logs(
    route_id: str,
    export_root: Path,
    segment_service: SegmentService,
    segment_artifact_service: SegmentArtifactService,
    artifact_service: ArtifactService,
    minio_service: MinioService,
) -> None:
    logger.info("Downloading route logs route_id=%s", route_id)
    segments = await segment_service.get_segments_by_route(route_id=route_id)

    for segment in segments:
        log_path = export_root / "segments" / str(segment.segment_id) / "logs" / "log.json"

        log_artifact = await segment_artifact_service.get_segment_artifact(
            route_id=route_id,
            segment_id=segment.segment_id,
            role=ArtifactRole.SEGMENT_LOG,
        )
        if log_artifact is None:
            raise ValueError(
                f"Missing segment log artifact row for route_id={route_id} segment_id={segment.segment_id}"
            )

        artifact = await artifact_service.get_artifact(
            artifact_id=log_artifact.artifact_id
        )
        if artifact is None:
            raise ValueError(
                f"Missing artifact for segment log artifact id={log_artifact.artifact_id}"
            )
        minio_service.download_artifact(artifact=artifact, dest_path=log_path)


async def _download_job_outputs(
    selected_job_runs: list[DatasetExportJobRun],
    export_root: Path,
    job_segment_run_service: JobSegmentRunService,
    artifact_service: ArtifactService,
    minio_service: MinioService,
) -> None:
    logger.info(
        "Downloading selected job outputs selected_job_runs=%s",
        [
            (
                selected_job_run.job_def_id,
                selected_job_run.job_run_num,
                selected_job_run.camera.value,
            )
            for selected_job_run in selected_job_runs
        ],
    )
    for selected_job_run in selected_job_runs:
        segment_runs = await job_segment_run_service.get_segments_by_job_run(
            job_run_num=selected_job_run.job_run_num,
            job_def_id=selected_job_run.job_def_id,
            route_id=selected_job_run.route_id,
            camera=selected_job_run.camera,
        )
        if not segment_runs:
            raise ValueError(
                "No job segment runs found for "
                f"job_def_id={selected_job_run.job_def_id} "
                f"job_run_num={selected_job_run.job_run_num} "
                f"route_id={selected_job_run.route_id} "
                f"camera={selected_job_run.camera.value}"
            )

        for segment_run in segment_runs:
            if segment_run.artifact_id is None:
                raise ValueError(f"Cannot export job {selected_job_run.job_def_id}, run {selected_job_run.job_run_num}: segment {segment_run.segment_id} has no annotation output (status: {segment_run.status.value}). Repair the annotation job first; completed segment outputs are preserved.")

            artifact = await artifact_service.get_artifact(
                artifact_id=segment_run.artifact_id
            )
            if artifact is None:
                raise ValueError(
                    f"Missing artifact for job segment run artifact id={segment_run.artifact_id}"
                )

            output_path = (
                export_root
                / "job_runs"
                / selected_job_run.camera.value
                / str(selected_job_run.job_def_id)
                / str(selected_job_run.job_run_num)
                / "segments"
                / str(segment_run.segment_id)
                / "data.json"
            )
            if artifact.kind == ArtifactKind.ZIP:
                archive_path = output_path.with_name("depth-labels.zip")
                minio_service.download_artifact(artifact=artifact, dest_path=archive_path)
                extract_depth_archive(archive_path, output_path.parent)
                archive_path.unlink()
            else:
                minio_service.download_artifact(artifact=artifact, dest_path=output_path)


def _write_manifest(
    export_root: Path,
    route_id: str,
    export_id: int,
    camera_views: list[str],
    selected_job_runs: list[DatasetExportJobRun],
) -> None:
    logger.info("Writing dataset export manifest export_id=%s", export_id)
    manifest = {
        "export_id": export_id,
        "route_id": route_id,
        "camera_views": camera_views,
        "job_runs": [
            {
                "job_def_id": selected_job_run.job_def_id,
                "job_run_num": selected_job_run.job_run_num,
                "camera": selected_job_run.camera.value,
            }
            for selected_job_run in selected_job_runs
        ],
    }
    manifest_path = export_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _zip_export(export_root: Path, zip_path: Path) -> None:
    logger.info("Creating dataset export zip zip_path=%s", zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for path in export_root.rglob("*"):
            if path.is_file():
                zip_file.write(path, path.relative_to(export_root.parent))


async def _process_dataset_export(
    dataset_export_service: DatasetExportService,
    dataset_export: DatasetExport,
    segment_service: SegmentService,
    frame_service: FrameService,
    frame_artifact_service: FrameArtifactService,
    segment_artifact_service: SegmentArtifactService,
    artifact_service: ArtifactService,
    job_segment_run_service: JobSegmentRunService,
    minio_service: MinioService,
    session: AsyncSession,
) -> None:
    export_id = dataset_export.export_id  # plain values, safe to use after a rollback
    export_route_id = dataset_export.route_id
    logger.info("Processing dataset export export_id=%s", dataset_export.export_id)
    await dataset_export_service.set_status(
        export_id=dataset_export.export_id,
        status=DatasetExportStatus.RUNNING,
    )
    await session.commit()

    try:
        selected_job_runs = await dataset_export_service.get_selected_job_runs(
            export_id=dataset_export.export_id
        )

        with TemporaryDirectory(dir=DATA_DIR) as temp_dir:
            temp_root = Path(temp_dir)
            export_root = temp_root / f"route_{dataset_export.route_id.replace('|', '_')}"
            export_root.mkdir(parents=True, exist_ok=True)

            await _download_job_outputs(
                selected_job_runs=selected_job_runs,
                export_root=export_root,
                job_segment_run_service=job_segment_run_service,
                artifact_service=artifact_service,
                minio_service=minio_service,
            )
            link_depth_to_coco(export_root)

            await _download_route_images(
                route_id=dataset_export.route_id,
                camera_views=dataset_export.camera_views,
                export_root=export_root,
                segment_service=segment_service,
                frame_service=frame_service,
                frame_artifact_service=frame_artifact_service,
                artifact_service=artifact_service,
                minio_service=minio_service,
            )
            await _download_route_logs(
                route_id=dataset_export.route_id,
                export_root=export_root,
                segment_service=segment_service,
                segment_artifact_service=segment_artifact_service,
                artifact_service=artifact_service,
                minio_service=minio_service,
            )
            _write_manifest(
                export_root=export_root,
                route_id=dataset_export.route_id,
                export_id=dataset_export.export_id,
                camera_views=dataset_export.camera_views,
                selected_job_runs=selected_job_runs,
            )

            zip_path = temp_root / f"{dataset_export.export_id}.zip"
            _zip_export(export_root=export_root, zip_path=zip_path)

            upload_result = minio_service.put_dataset_export_zip(
                route_id=dataset_export.route_id,
                export_id=dataset_export.export_id,
                file_path=zip_path,
            )
            artifact = await artifact_service.create_artifact(
                bucket=minio_service.bucket_name,
                object_key=upload_result.object_name,
                kind=ArtifactKind.ZIP,
            )
            await dataset_export_service.set_zip_artifact(
                export_id=dataset_export.export_id,
                artifact_id=artifact.artifact_id,
            )
            await dataset_export_service.set_status(
                export_id=dataset_export.export_id,
                status=DatasetExportStatus.SUCCEEDED,
            )
            await session.commit()
            logger.info(
                "Dataset export succeeded export_id=%s artifact_id=%s",
                dataset_export.export_id,
                artifact.artifact_id,
            )
            await record_audit(
                "dataset_export.finished", OUTCOME_SUCCESS,
                entity_type="dataset_export", entity_id=f"{export_id}/{export_route_id}", route_id=export_route_id,
            )
    except Exception as exc:
        logger.exception("Dataset export failed export_id=%s", export_id)
        error = describe_exception(exc)
        await record_failure(
            session,
            logger,
            f"dataset export {export_id}",
            lambda: dataset_export_service.set_error(export_id=export_id, error=error),
        )
        await record_audit(
            "dataset_export.finished", OUTCOME_FAILURE,
            entity_type="dataset_export", entity_id=f"{export_id}/{export_route_id}", route_id=export_route_id,
            message=error, error_code=error_code_of(exc),
        )


async def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(build_database_url(), pool_pre_ping=True)
    session_local = async_sessionmaker(bind=engine, expire_on_commit=False)
    configure_audit(session_local, source="dataset_export_worker")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        async with session_local() as session:
            dataset_export_service = build_dataset_export_service(session=session)
            segment_service = build_segment_service(session=session)
            frame_service = build_frame_service(session=session)
            frame_artifact_service = build_frame_artifact_service(session=session)
            segment_artifact_service = build_segment_artifact_service(session=session)
            artifact_service = build_artifact_service(session=session)
            job_segment_run_service = build_job_segment_run_service(session=session)
            minio_service = MinioService()

            await _mark_stale_running_exports_as_failed(
                dataset_export_service=dataset_export_service,
                session=session,
            )

            while not stop_event.is_set():
                dataset_export = await dataset_export_service.get_next_dataset_export_by_status(
                    status=DatasetExportStatus.QUEUED
                )
                if dataset_export is None:
                    logger.info("No queued dataset exports found")
                    await session.rollback()
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                await _process_dataset_export(
                    dataset_export_service=dataset_export_service,
                    dataset_export=dataset_export,
                    segment_service=segment_service,
                    frame_service=frame_service,
                    frame_artifact_service=frame_artifact_service,
                    segment_artifact_service=segment_artifact_service,
                    artifact_service=artifact_service,
                    job_segment_run_service=job_segment_run_service,
                    minio_service=minio_service,
                    session=session,
                )
    finally:
        await engine.dispose()
        logger.info("Dataset export worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
