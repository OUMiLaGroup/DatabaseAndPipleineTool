from datetime import datetime

from pydantic import BaseModel, ConfigDict

from db.models.route import RouteStatus


class CreateRouteRequest(BaseModel):
    route_id: str
    status: RouteStatus = RouteStatus.DOWNLOAD_QUEUE


class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    route_id: str
    file_path: str | None
    status: RouteStatus
    created_at: datetime
    download_error: dict[str, str] | None = None
