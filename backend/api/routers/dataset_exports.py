import logging

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_session, get_transactional_session
from schemas.dataset_export import (
    CreateDatasetExportRequest,
    DatasetExportJobRunSelectionResponse,
    DatasetExportResponse,
)
from services.errors import DatasetExportNotFoundError
from services.minio_service import MinioService
from utilities.service_builder_utilities import build_dataset_export_service

logger = logging.getLogger(__name__)

dataset_exports_router = APIRouter(
    prefix="/dataset-exports",
)


def _to_response(dataset_export, selected_job_runs) -> DatasetExportResponse:
    return DatasetExportResponse(
        export_id=dataset_export.export_id,
        route_id=dataset_export.route_id,
        camera_views=dataset_export.camera_views,
        status=dataset_export.status,
        error=dataset_export.error,
        queued_at=dataset_export.queued_at,
        started_at=dataset_export.started_at,
        finished_at=dataset_export.finished_at,
        zip_artifact_id=dataset_export.zip_artifact_id,
        job_runs=[
            DatasetExportJobRunSelectionResponse(
                job_def_id=selected_job_run.job_def_id,
                job_run_num=selected_job_run.job_run_num,
                camera=selected_job_run.camera,
            )
            for selected_job_run in selected_job_runs
        ],
    )


@dataset_exports_router.get("/", response_model=list[DatasetExportResponse])
async def list_dataset_exports(
    route_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[DatasetExportResponse]:
    logger.info("Listing dataset exports route_id=%s", route_id)
    dataset_export_service = build_dataset_export_service(session=session)
    if route_id is None:
        dataset_exports = await dataset_export_service.list_dataset_exports()
    else:
        dataset_exports = await dataset_export_service.get_dataset_exports_by_route_id(
            route_id=route_id
        )

    responses: list[DatasetExportResponse] = []
    for dataset_export in dataset_exports:
        selected_job_runs = await dataset_export_service.get_selected_job_runs(
            dataset_export.export_id
        )
        responses.append(_to_response(dataset_export, selected_job_runs))
    return responses


@dataset_exports_router.get("/{export_id}", response_model=DatasetExportResponse)
async def get_dataset_export(
    export_id: int,
    session: AsyncSession = Depends(get_session),
) -> DatasetExportResponse:
    logger.info("Getting dataset export export_id=%s", export_id)
    dataset_export_service = build_dataset_export_service(session=session)
    dataset_export = await dataset_export_service.get_dataset_export(export_id)
    if dataset_export is None:
        raise DatasetExportNotFoundError(export_id)

    selected_job_runs = await dataset_export_service.get_selected_job_runs(export_id)
    return _to_response(dataset_export, selected_job_runs)


@dataset_exports_router.post(
    "/",
    response_model=DatasetExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset_export(
    payload: CreateDatasetExportRequest,
    session: AsyncSession = Depends(get_transactional_session),
) -> DatasetExportResponse:
    logger.info("Creating dataset export route_id=%s", payload.route_id)
    dataset_export_service = build_dataset_export_service(session=session)
    dataset_export = await dataset_export_service.create_dataset_export(
        route_id=payload.route_id,
        camera_views=payload.camera_views,
        job_runs=[
            (job_run.job_def_id, job_run.job_run_num, job_run.camera)
            for job_run in payload.job_runs
        ],
    )
    selected_job_runs = await dataset_export_service.get_selected_job_runs(
        dataset_export.export_id
    )
    return _to_response(dataset_export, selected_job_runs)


@dataset_exports_router.get("/{export_id}/download")
async def get_dataset_export_download(
    export_id: int,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    logger.info("Getting dataset export download export_id=%s", export_id)
    dataset_export_service = build_dataset_export_service(session=session)
    dataset_export, artifact = await dataset_export_service.get_download_artifact(
        export_id=export_id
    )
    minio_service = MinioService()
    filename = f"route_{dataset_export.route_id.replace('|', '_')}_export_{dataset_export.export_id}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        minio_service.stream_object(
            bucket_name=artifact.bucket,
            object_key=artifact.object_key,
        ),
        media_type="application/zip",
        headers=headers,
    )


@dataset_exports_router.delete("/{export_id}")
async def delete_dataset_export(
    export_id: int,
    session: AsyncSession = Depends(get_transactional_session),
):
    logger.info("Deleting dataset export export_id=%s", export_id)
    dataset_export_service = build_dataset_export_service(session=session)
    await dataset_export_service.delete_dataset_export(export_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
