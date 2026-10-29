import logging

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, Response, status, APIRouter

from api.dependencies import get_session, get_transactional_session
from db.enums import RouteStatus
from db.models.route import Route
from schemas.route import CreateRouteRequest, RouteResponse
from services.errors import RouteNotFoundError
from services.route_service import RouteService
from utilities.service_builder_utilities import build_delete_service, build_route_service


logger = logging.getLogger(__name__)

routes_router = APIRouter(
    prefix="/routes",
)

@routes_router.get("/", response_model=list[RouteResponse])
async def list_routes(
    session: AsyncSession = Depends(get_session),
) -> list[Route]:
    logging.info("get routes")
    route_service = build_route_service(session=session)
    return await route_service.list_routes()

@routes_router.get("/{route_id:path}", response_model=RouteResponse)
async def get_route(
    route_id: str,
    session: AsyncSession = Depends(get_session),
) -> Route:
    logging.info(f"Getting route {route_id}")
    route_service = build_route_service(session=session)
    route = await route_service.get_route(route_id=route_id)
    if route is None:
        raise RouteNotFoundError(route_id=route_id)
    return route

@routes_router.post("/", response_model=RouteResponse, status_code=status.HTTP_201_CREATED)
async def create_route(
    payload: CreateRouteRequest,
    session: AsyncSession = Depends(get_transactional_session)
) -> Route:
    logging.info("create routes")
    route_service: RouteService = build_route_service(session=session)
    return await route_service.create_route(
        route_id=payload.route_id,
        status=RouteStatus.DOWNLOAD_QUEUE
    )

@routes_router.delete("/{route_id:path}")
async def delete_route(
    route_id: str,
    session: AsyncSession = Depends(get_transactional_session),
):
    logging.info("deletee route")
    service = build_delete_service(session=session)
    await service.delete_route(route_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


