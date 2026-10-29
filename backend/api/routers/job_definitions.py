import logging

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, Response, status, APIRouter

from api.dependencies import get_session, get_transactional_session
from db.models.job_definition import JobDefinition
from schemas.job_definition import CreateJobDefinitionRequest, JobDefinitionResponse
from services.errors import JobDefinitionNotFoundError
from services.job_definition_service import JobDefinitionService
from utilities.service_builder_utilities import build_job_definition_service

logger = logging.getLogger(__name__)

job_definitions_router = APIRouter(
    prefix="/job-definitions",
)

@job_definitions_router.get("/", response_model=list[JobDefinitionResponse])
async def list_job_definitions(
    session: AsyncSession = Depends(get_session),
) -> list[JobDefinition]:
    logging.info("get job definitions")
    job_definition_service = build_job_definition_service(session=session)
    return await job_definition_service.list_job_definitions()

@job_definitions_router.get("/{job_def_id}", response_model=JobDefinitionResponse)
async def get_job_definition(
    job_def_id: int,
    session: AsyncSession = Depends(get_session),
) -> JobDefinition:
    logging.info(f"Getting job definition {job_def_id}")
    job_definition_service = build_job_definition_service(session=session)
    job_definition = await job_definition_service.get_job_definition(job_def_id=job_def_id)
    if job_definition is None:
        raise JobDefinitionNotFoundError(job_def_id)
    return job_definition

@job_definitions_router.post("/", response_model=JobDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def create_job_definition(
    payload: CreateJobDefinitionRequest,
    session: AsyncSession = Depends(get_transactional_session),
) -> JobDefinition:
    logging.info("create job definition")
    job_definition_service: JobDefinitionService = build_job_definition_service(session=session)
    return await job_definition_service.create_job_definition(
        type=payload.type,
        implementation_key=payload.implementation_key,
        name=payload.name,
        config=payload.config,
        description=payload.description,
    )

@job_definitions_router.delete("/{job_def_id}")
async def delete_job_definition(
    job_def_id: int,
    session: AsyncSession = Depends(get_transactional_session),
):
    logging.info("delete job definition")
    job_definition_service = build_job_definition_service(session=session)
    await job_definition_service.delete_job_definition(job_def_id=job_def_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
