from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator
from depth_config import DepthConfig

from db.enums import JobType


class CreateJobDefinitionRequest(BaseModel):
    type: JobType
    implementation_key: str
    name: str
    config: dict
    description: str | None = None

    @model_validator(mode="after")
    def validate_depth(self):
        if self.type == JobType.DEPTH or self.implementation_key == "depth_anything_3":
            if self.type != JobType.DEPTH or self.implementation_key != "depth_anything_3":
                raise ValueError("Depth Anything 3 requires type depth and implementation_key depth_anything_3.")
            self.config = DepthConfig.model_validate(self.config).model_dump(mode="json")
        return self


class JobDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_def_id: int
    type: JobType
    implementation_key: str
    name: str
    description: str | None
    config: dict
    created_at: datetime
