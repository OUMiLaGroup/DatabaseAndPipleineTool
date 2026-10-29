from datetime import datetime

from pydantic import BaseModel, ConfigDict

from db.enums import CameraType, JobSegmentRunImportStatus, JobSegmentRunStatus, SegmentStatus


class JobSegmentRunResponse(BaseModel):
    job_run_num: int
    route_id: str
    job_def_id: int
    camera: CameraType
    segment_id: int
    status: JobSegmentRunStatus
    # Why this segment failed during the job run
    error: str | None = None

class CreateSegmentRequest(BaseModel):
    route_id: str
    segment_id: int
    start_time: datetime
    end_time: datetime
    status: SegmentStatus = SegmentStatus.DOWNLOAD_QUEUE

class SegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    route_id: str
    segment_id: int
    start_time: datetime
    end_time: datetime
    status: SegmentStatus
    created_at: datetime
    # Why the segment failed to download/upload
    error: str | None = None

class SegmentJobImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    route_id: str
    job_run_num: int
    job_def_id: int
    segment_id: int
    status: JobSegmentRunImportStatus
    task_id: int | None
    created_at: datetime
    error_message: str | None
    task_url: str | None
    camera: CameraType



