from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    source: str
    action: str
    outcome: str
    entity_type: str | None
    entity_id: str | None
    route_id: str | None
    message: str | None
    error_code: str | None
    request_id: str | None
    details: dict[str, Any] | None
