import logging

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, Response, status, APIRouter, HTTPException

from api.dependencies import get_session, get_transactional_session
from db.enums import CameraType, JobType
from depth_config import DepthConfig
from db.models.job_run import JobRun
from schemas.job_run import CreateJobRunRequest, JobRunResponse
from services.errors import JobRunNotFoundError
from services.job_run_service import JobRunService
from utilities.service_builder_utilities import build_delete_service, build_job_run_service
from utilities.service_builder_utilities import build_job_definition_service

logger = logging.getLogger(__name__)

job_runs_router = APIRouter(
    prefix="/job-runs",
)

@job_runs_router.get("/by-route/{route_id}", response_model=list[JobRunResponse])
async def list_job_runs_by_route(
    route_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[JobRun]:
    logging.info(f"get job runs for route {route_id}")
    job_run_service = build_job_run_service(session=session)
    return await job_run_service.list_job_runs_by_route(route_id)


@job_runs_router.get("/", response_model=list[JobRunResponse])
async def list_job_runs(
    session: AsyncSession = Depends(get_session),
) -> list[JobRun]:
    logging.info("get job runs")
    job_run_service = build_job_run_service(session=session)
    return await job_run_service.list_job_runs()


@job_runs_router.get("/{route_id:path}/{job_def_id}/{job_run_num}/{camera}", response_model=JobRunResponse)
async def get_job_run(
    job_def_id: int,
    job_run_num: int,
    route_id: str,
    camera: CameraType,
    session: AsyncSession = Depends(get_session),
) -> JobRun:
    logging.info(f"Getting job run ({job_def_id=}, {job_run_num=}, {route_id=})")
    job_run_service = build_job_run_service(session=session)
    job_run = await job_run_service.get_job_run(
        job_def_id=job_def_id,
        job_run_num=job_run_num,
        route_id=route_id,
        camera=camera,
    )
    if job_run is None:
        raise JobRunNotFoundError(
            job_run_num=job_run_num,
            job_def_id=job_def_id,
            route_id=route_id
        )
    return job_run


@job_runs_router.post("/", response_model=JobRunResponse, status_code=status.HTTP_201_CREATED)
async def create_job_run(
    payload: CreateJobRunRequest,
    session: AsyncSession = Depends(get_transactional_session),
) -> JobRun:
    logging.info("create job run")
    definition = await build_job_definition_service(session=session).get_job_definition(payload.job_def_id)
    if definition is not None and definition.type == JobType.DEPTH:
        try:
            DepthConfig.model_validate(definition.config).calibration_for(payload.camera.value)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    job_run_service: JobRunService = build_job_run_service(session=session)
    return await job_run_service.create_job_run(
        job_def_id=payload.job_def_id,
        route_id=payload.route_id,
        camera=payload.camera,
    )


@job_runs_router.post("/cancel", response_model=JobRunResponse)
async def cancel_job_run(
    job_def_id: int,
    job_run_num: int,
    route_id: str,
    camera: CameraType,
    session: AsyncSession = Depends(get_transactional_session)
) -> JobRun:
    logging.info("Cancel job run")
    job_run_service = build_job_run_service(session=session)
    return await job_run_service.cancel_job_run(
        job_run_num=job_run_num,
        job_def_id=job_def_id,
        route_id=route_id,
        camera=camera
    )

@job_runs_router.post("/requeue", response_model=JobRunResponse)
async def requeue_job_run(
    job_def_id: int,
    job_run_num: int,
    route_id: str,
    camera: CameraType,
    session: AsyncSession = Depends(get_transactional_session)
) -> JobRun:
    logging.info("Requeue job run")
    job_run_service = build_job_run_service(session=session)
    return await job_run_service.requeue_job_run(
        job_run_num=job_run_num,
        job_def_id=job_def_id,
        route_id=route_id,
        camera=camera
    )

@job_runs_router.delete("/")
async def delete_job_run(
    job_def_id: int,
    job_run_num: int,
    route_id: str,
    camera: CameraType,
    session: AsyncSession = Depends(get_transactional_session),
):
    logging.info("delete job run")
    delete_service = build_delete_service(session=session)
    await delete_service.delete_job_run(
        job_run_num=job_run_num,
        job_def_id=job_def_id,
        route_id=route_id,
        camera=camera
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
