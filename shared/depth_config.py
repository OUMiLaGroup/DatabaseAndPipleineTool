"""Validation shared by the API and inference worker (no ML imports)."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class CameraCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fx: float = Field(gt=0)
    fy: float = Field(gt=0)
    cx: float | None = None
    cy: float | None = None


class DepthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    model_name: Literal["depth-anything/DA3METRIC-LARGE"] = "depth-anything/DA3METRIC-LARGE"
    model_revision: Literal["4010e39f3634a45bc60553321fb49fb760bd594e"] = "4010e39f3634a45bc60553321fb49fb760bd594e"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    process_res: int = Field(default=504, ge=140, le=1008, multiple_of=14)
    calibrations: dict[Literal["front_regular", "front_wide", "driver"], CameraCalibration] = Field(default_factory=dict)
    require_metric: bool = False

    def calibration_for(self, camera: str) -> CameraCalibration | None:
        calibration = self.calibrations.get(camera)
        if self.require_metric and calibration is None:
            raise ValueError(f"Depth in meters requires calibration for {camera}. Add width, height, fx and fy to calibrations in the job definition.")
        return calibration
