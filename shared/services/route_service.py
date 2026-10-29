from db.models.route import Route, RouteStatus
from repositories.route_repository import RouteRepository
from services.errors import RouteAlreadyExistsError, RouteNotFoundError
from utilities.open_pilot_utilities import is_valid_route_str


class RouteService:
    def __init__(self, route_repository: RouteRepository) -> None:
        self._route_repository = route_repository

    async def list_routes(self) -> list[Route]:
        return await self._route_repository.list_all()

    async def get_routes_by_status(self, status: RouteStatus) -> list[Route]:
        return await self._route_repository.get_by_status(status)

    async def get_next_route_by_status(self, status: RouteStatus) -> Route | None:
        return await self._route_repository.get_next_by_status(status)

    async def get_route(self, route_id: str) -> Route | None:
        return await self._route_repository.get_by_id(route_id)

    async def create_route(
        self,
        route_id: str,
        status: RouteStatus = RouteStatus.DOWNLOAD_QUEUE,
    ) -> Route:
        route_id = route_id.strip().replace('/', '|', 1)
        existing_route = await self._route_repository.get_by_id(route_id)
        if existing_route is not None:
            raise RouteAlreadyExistsError(route_id)

        if not is_valid_route_str(route_id):
            raise ValueError(f"'{route_id}' is not a valid route string")

        return await self._route_repository.create(
            route_id=route_id,
            status=status,
        )

    async def set_status(self, route_id: str, status: RouteStatus, error: str | None = None) -> Route:
        """Set the route status. Pass ``error`` to record why it failed (or a warning).

        ``error`` is only written when given, so later status changes keep an earlier message.
        """
        route = await self._route_repository.get_by_id(route_id)
        if route is None:
            raise RouteNotFoundError(route_id)

        route.status = status
        if error is not None:
            route.error = error
        return await self._route_repository.save(route)

    async def set_file_path(self, route_id: str, file_path: str | None) -> Route:
        route = await self._route_repository.get_by_id(route_id)
        if route is None:
            raise RouteNotFoundError(route_id)

        route.file_path = file_path
        return await self._route_repository.save(route)

    async def set_download_error(self, route_id: str, error: dict | None) -> Route:
        route = await self._route_repository.get_by_id(route_id)
        if route is None:
            raise RouteNotFoundError(route_id)
        meta = dict(route.meta or {})
        if error is None:
            meta.pop('download_error', None)
        else:
            meta['download_error'] = error
        route.meta = meta
        return await self._route_repository.save(route)

    async def delete_route(self, route_id: str) -> None:
        route = await self._route_repository.get_by_id(route_id)
        if route is None:
            raise RouteNotFoundError(route_id)

        await self._route_repository.delete(route)
