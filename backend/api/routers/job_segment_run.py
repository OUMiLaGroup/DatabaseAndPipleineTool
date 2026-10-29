import logging

from fastapi import APIRouter, Depends, Response, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_session, get_transactional_session
from db.enums import CameraType, JobSegmentRunImportStatus, JobType
from db.models.job_segment_run import JobSegmentRun
from db.models.job_segment_run_import import JobSegmentRunImport
from schemas.segment import JobSegmentRunResponse, SegmentJobImportResponse
from utilities.service_builder_utilities import build_job_segment_run_import_service, build_job_segment_run_service
from utilities.service_builder_utilities import build_job_definition_service

logger = logging.getLogger(__name__)

job_segment_run_router = APIRouter(
    prefix="/job_segment_run",
)

@job_segment_run_router.get("/cvat-import", response_model=SegmentJobImportResponse | None)
async def get_cvat_job_segment_run_imports(
    route_id: str,
    job_def_id: int,
    job_run_num: int,
    segment_id: int,
    camera: CameraType,
    session: AsyncSession = Depends(get_session)
) -> JobSegmentRunImport | None:
    logging.info("Getting cvat import job segment run")
    job_segment_run_review_service = build_job_segment_run_import_service(session=session)
    return await job_segment_run_review_service.get_by_id(
        job_run_num=job_run_num,
        job_def_id=job_def_id,
        route_id=route_id,
        segment_id=segment_id,
        camera=camera
    )

@job_segment_run_router.get("/cvat-import/{route_id:path}", response_model=list[SegmentJobImportResponse])
async def get_cvat_import_for_route(
    route_id: str,
    session: AsyncSession = Depends(get_session)
) -> list[JobSegmentRunImport]:
    logging.info(f"Getting cvat import for route {route_id}")
    job_segment_run_review_service = build_job_segment_run_import_service(session=session)
    return await job_segment_run_review_service.get_by_route_id(
        route_id=route_id
    )


@job_segment_run_router.get("/{route_id}/{segment_id}", response_model=list[JobSegmentRunResponse])
async def get_job_segment_runs_by_segment(
    route_id: str,
    segment_id: int,
    session: AsyncSession = Depends(get_session)
) -> list[JobSegmentRun]:
    logging.info(f"Getting job segment runs for {route_id}/{segment_id}")
    job_segment_run_service = build_job_segment_run_service(session=session)
    return await job_segment_run_service.get_job_segment_runs_by_route_and_segment(
        route_id=route_id,
        segment_id=segment_id
    )

@job_segment_run_router.get("/{route_id}", response_model=list[JobSegmentRunResponse])
async def get_job_segment_runs_by_route(
    route_id: str,
    session: AsyncSession = Depends(get_session)
) -> list[JobSegmentRun]:
    logging.info(f"fGetting job segment runs for {route_id}")
    job_segment_run_service = build_job_segment_run_service(session=session)
    return await job_segment_run_service.get_job_segment_runs_by_route_id(
        route_id=route_id
    )


@job_segment_run_router.post("/cvat-import", response_model=SegmentJobImportResponse)
async def import_job_segment_run_to_cvat(
    route_id: str,
    job_def_id: int,
    job_run_num: int,
    segment_id: int,
    camera: CameraType,
    session: AsyncSession = Depends(get_transactional_session)
) -> JobSegmentRunImport:
    logging.info("Importing job segment run to cvat")
    definition = await build_job_definition_service(session=session).get_job_definition(job_def_id)
    if definition is not None and definition.type == JobType.DEPTH:
        raise HTTPException(400, "Pixel depth maps are exported as NPZ labels, not CVAT COCO boxes. Use Export on the route's depth job.")
    job_segment_run_review_service = build_job_segment_run_import_service(session=session)
    job_segment_run_review = await job_segment_run_review_service.create(
        job_run_num=job_run_num,
        job_def_id=job_def_id,
        route_id=route_id,
        segment_id=segment_id,
        camera=camera,
    )

    return job_segment_run_review

@job_segment_run_router.delete("/cvat-import")
async def delete_job_segment_run_in_cvat(
    route_id: str,
    job_def_id: int,
    job_run_num: int,
    segment_id: int,
    camera: CameraType,
    session: AsyncSession = Depends(get_transactional_session)
):
    logging.info("Removing job segment run from cvat")
    job_segment_run_review_service = build_job_segment_run_import_service(session=session)
    await job_segment_run_review_service.set_status(
        job_run_num=job_run_num,
        job_def_id=job_def_id,
        route_id=route_id,
        segment_id=segment_id,
        camera=camera,
        status=JobSegmentRunImportStatus.QUEUED_FOR_REMOVAL
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)



