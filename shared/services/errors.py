"""
Custom exceptions for the services layer.

Every error here inherits from ``PipelineError``. Each error carries:

* ``code``        - a stable, machine-readable identifier (e.g. ``ROUTE_NOT_FOUND``).
                    The frontend and the error guide key off this, so do not rename codes.
* ``status_code`` - the HTTP status the API should return for this error.
* ``hint``        - a short, user-facing suggestion for how to fix the problem.
* ``context``     - the identifiers involved (route_id, job_def_id, ...) to help debugging.

The backend registers one exception handler for ``PipelineError`` (see ``backend/main.py``)
that turns any of these into a consistent JSON response:

    {
        "detail": "Route abc not found",
        "code": "ROUTE_NOT_FOUND",
        "hint": "Check the route ID ...",
        "context": {"route_id": "abc"},
        "request_id": "4f1c..."
    }

To add a new error: subclass ``PipelineError`` (or one of the base classes below), set
``code``, ``status_code`` and ``hint``, and raise it. No new handler is needed in main.py.

Status codes are plain ints so the workers can import this module without FastAPI.
"""
from typing import Any
from uuid import UUID

from db.models.segment_artifact import ArtifactRole

HTTP_400_BAD_REQUEST = 400
HTTP_404_NOT_FOUND = 404
HTTP_409_CONFLICT = 409
HTTP_503_SERVICE_UNAVAILABLE = 503


class PipelineError(ValueError):
    """Base class for all expected (handled) errors in the pipeline."""

    code: str = "PIPELINE_ERROR"
    status_code: int = HTTP_400_BAD_REQUEST
    hint: str | None = None

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if hint is not None:
            self.hint = hint
        self.context: dict[str, Any] = context or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "detail": self.message,
            "code": self.code,
            "hint": self.hint,
            "context": {key: _jsonable(value) for key, value in self.context.items()},
        }


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class NotFoundError(PipelineError):
    code = "NOT_FOUND"
    status_code = HTTP_404_NOT_FOUND


class AlreadyExistsError(PipelineError):
    code = "ALREADY_EXISTS"
    status_code = HTTP_409_CONFLICT


class ConflictError(PipelineError):
    code = "CONFLICT"
    status_code = HTTP_409_CONFLICT


_MISSING_FILE_HINT = (
    "The stored file for this item could not be found. Check that MinIO is running "
    "(http://localhost:9001) and the bucket still exists. Deleting and re-importing "
    "the route regenerates its frames and artifacts."
)


# ─── Routes ──────────────────────────────────────────────────────────────────

class RouteAlreadyExistsError(AlreadyExistsError):
    code = "ROUTE_ALREADY_EXISTS"
    hint = (
        "This route has already been imported. Open it from the dashboard, or delete "
        "it first if you want to import it again."
    )

    def __init__(self, route_id: str) -> None:
        super().__init__(f"Route {route_id} already exists", context={"route_id": route_id})


class RouteNotFoundError(NotFoundError):
    code = "ROUTE_NOT_FOUND"
    hint = (
        "Check the route ID (format: <dongle_id>|<log_id>, e.g. "
        "db478799b6f9f210|0000000e--9ecd39f6bc). The route may have been deleted; "
        "refresh the dashboard."
    )

    def __init__(self, route_id: str) -> None:
        super().__init__(f"Route {route_id} not found", context={"route_id": route_id})


class RouteNotReadyForJobRunError(ConflictError):
    code = "ROUTE_NOT_READY"
    hint = (
        "Job runs can only be created once the route status is UPLOADED. Wait for the "
        "download and upload workers to finish. If the route is FAILED, delete it and "
        "import it again."
    )

    def __init__(self, route_id: str, status: str) -> None:
        super().__init__(
            f"Route {route_id} is not ready for job creation; current status is {status}",
            context={"route_id": route_id, "status": status},
        )


class RouteDeleteError(ConflictError):
    code = "ROUTE_DELETE_BLOCKED"
    hint = "Wait for the route's active jobs and CVAT imports to finish, then try again."

    def __init__(self, reason: str):
        super().__init__(reason)


# ─── Dataset exports ─────────────────────────────────────────────────────────

class DatasetExportNotFoundError(NotFoundError):
    code = "DATASET_EXPORT_NOT_FOUND"
    hint = "The export may have been deleted. Refresh the page to see the current exports."

    def __init__(self, export_id: int) -> None:
        super().__init__(f"Dataset export {export_id} not found", context={"export_id": export_id})


class DatasetExportValidationError(PipelineError):
    code = "DATASET_EXPORT_INVALID"
    status_code = HTTP_400_BAD_REQUEST
    hint = (
        "An export needs: a route with status UPLOADED, at least one camera view (no "
        "duplicates) that exists on the route, and only job runs with status SUCCEEDED."
    )

    def __init__(self, message: str) -> None:
        super().__init__(message)


class DatasetExportDeletionConflictError(ConflictError):
    code = "DATASET_EXPORT_RUNNING"
    hint = "Wait for the export to finish (SUCCEEDED or FAILED), then delete it."

    def __init__(self, export_id: int) -> None:
        super().__init__(
            f"Dataset export {export_id} cannot be deleted while RUNNING",
            context={"export_id": export_id},
        )


# ─── Segments & frames ───────────────────────────────────────────────────────

class SegmentAlreadyExistsError(AlreadyExistsError):
    code = "SEGMENT_ALREADY_EXISTS"

    def __init__(self, route_id: str, segment_id: int) -> None:
        super().__init__(
            f"Segment {segment_id} for route {route_id} already exists",
            context={"route_id": route_id, "segment_id": segment_id},
        )


class SegmentNotFoundError(NotFoundError):
    code = "SEGMENT_NOT_FOUND"
    hint = (
        "This segment does not exist for the route. Segments that failed to download "
        "are skipped; check the segment list on the route page."
    )

    def __init__(self, route_id: str, segment_id: int) -> None:
        super().__init__(
            f"Segment {segment_id} for route {route_id} not found",
            context={"route_id": route_id, "segment_id": segment_id},
        )


class FrameAlreadyExistsError(AlreadyExistsError):
    code = "FRAME_ALREADY_EXISTS"

    def __init__(self, frame_pk: int) -> None:
        super().__init__(f"Frame {frame_pk} already exists", context={"frame_pk": frame_pk})


class FrameNotFoundError(NotFoundError):
    code = "FRAME_NOT_FOUND"
    hint = (
        "No frames were found. The segment may still be uploading, or it failed during "
        "upload; check the segment status on the route page."
    )

    def __init__(self, frame_pk: int) -> None:
        super().__init__(f"Frame {frame_pk} not found", context={"frame_pk": frame_pk})


# ─── Artifacts ───────────────────────────────────────────────────────────────

class ArtifactAlreadyExistsError(AlreadyExistsError):
    code = "ARTIFACT_ALREADY_EXISTS"

    def __init__(self, artifact_id: UUID) -> None:
        super().__init__(f"Artifact {artifact_id} already exists", context={"artifact_id": artifact_id})


class ArtifactNotFoundError(NotFoundError):
    code = "ARTIFACT_NOT_FOUND"
    hint = _MISSING_FILE_HINT

    def __init__(self, artifact_id: UUID) -> None:
        super().__init__(f"Artifact {artifact_id} not found", context={"artifact_id": artifact_id})


class SegmentArtifactAlreadyExistsError(AlreadyExistsError):
    code = "SEGMENT_ARTIFACT_ALREADY_EXISTS"

    def __init__(self, route_id: str, segment_id: int, role: ArtifactRole) -> None:
        super().__init__(
            f"Segment artifact with role {role} for segment {segment_id} and route {route_id} already exists",
            context={"route_id": route_id, "segment_id": segment_id, "role": role},
        )


class SegmentArtifactNotFoundError(NotFoundError):
    code = "SEGMENT_ARTIFACT_NOT_FOUND"
    hint = _MISSING_FILE_HINT

    def __init__(self, route_id: str, segment_id: int, role: ArtifactRole) -> None:
        super().__init__(
            f"Segment artifact with role {role} for segment {segment_id} and route {route_id} not found",
            context={"route_id": route_id, "segment_id": segment_id, "role": role},
        )


class FrameArtifactAlreadyExistsError(AlreadyExistsError):
    code = "FRAME_ARTIFACT_ALREADY_EXISTS"

    def __init__(self, frame_pk: int, role: ArtifactRole) -> None:
        super().__init__(
            f"Frame artifact with role {role} for frame {frame_pk} already exists",
            context={"frame_pk": frame_pk, "role": role},
        )


class FrameArtifactNotFoundError(NotFoundError):
    code = "FRAME_ARTIFACT_NOT_FOUND"
    hint = _MISSING_FILE_HINT

    def __init__(self, frame_pk: int, role: ArtifactRole) -> None:
        super().__init__(
            f"Frame artifact with role {role} for frame {frame_pk} not found",
            context={"frame_pk": frame_pk, "role": role},
        )


# ─── Job definitions ─────────────────────────────────────────────────────────

class JobDefinitionAlreadyExistsError(AlreadyExistsError):
    code = "JOB_DEFINITION_ALREADY_EXISTS"

    def __init__(self, job_def_id: int) -> None:
        super().__init__(f"Job definition {job_def_id} already exists", context={"job_def_id": job_def_id})


class JobDefinitionNotFoundError(NotFoundError):
    code = "JOB_DEFINITION_NOT_FOUND"
    hint = "The job definition may have been deleted. Refresh the Job Definitions page and pick another one."

    def __init__(self, job_def_id: int) -> None:
        super().__init__(f"Job definition {job_def_id} not found", context={"job_def_id": job_def_id})


# ─── Job runs ────────────────────────────────────────────────────────────────

def _job_run_context(job_run_num: int, job_def_id: int, route_id: str) -> dict[str, Any]:
    return {"job_run_num": job_run_num, "job_def_id": job_def_id, "route_id": route_id}


class JobRunAlreadyExistsError(AlreadyExistsError):
    code = "JOB_RUN_ALREADY_EXISTS"

    def __init__(self, job_run_num: int, job_def_id: int, route_id: str) -> None:
        super().__init__(
            f"Job run {(job_run_num, job_def_id, route_id)} already exists",
            context=_job_run_context(job_run_num, job_def_id, route_id),
        )


class JobRunNotFoundError(NotFoundError):
    code = "JOB_RUN_NOT_FOUND"
    hint = "The job run may have been deleted. Refresh the route page to see the current job runs."

    def __init__(self, job_run_num: int, job_def_id: int, route_id: str) -> None:
        super().__init__(
            f"Job run {(job_run_num, job_def_id, route_id)} not found",
            context=_job_run_context(job_run_num, job_def_id, route_id),
        )


class JobRunCancelError(ConflictError):
    code = "JOB_RUN_CANCEL_NOT_ALLOWED"
    hint = (
        "Only QUEUED job runs can be cancelled. A RUNNING job has to finish; finished "
        "job runs (SUCCEEDED, FAILED, CANCELLED) can be deleted instead."
    )

    def __init__(self, job_run_num: int, job_def_id: int, route_id: str, reason: str) -> None:
        super().__init__(
            f"Job run {(job_run_num, job_def_id, route_id)} cannot be cancelled: {reason}",
            context={**_job_run_context(job_run_num, job_def_id, route_id), "reason": reason},
        )


class JobRunRequeueError(ConflictError):
    code = "JOB_RUN_REQUEUE_NOT_ALLOWED"
    hint = (
        "Only CANCELLED job runs can be requeued. To retry a FAILED job run, create a "
        "new job run with the same job definition."
    )

    def __init__(self, job_run_num: int, job_def_id: int, route_id: str, reason: str) -> None:
        super().__init__(
            f"Job run {(job_run_num, job_def_id, route_id)} cannot be requeued: {reason}",
            context={**_job_run_context(job_run_num, job_def_id, route_id), "reason": reason},
        )


class JobRunningError(ConflictError):
    code = "JOB_RUN_ACTIVE"
    hint = (
        "This route still has QUEUED or RUNNING job runs. Cancel the queued ones and "
        "wait for running ones to finish, then try again."
    )

    def __init__(self, reason: str):
        super().__init__(reason)


class JobFrameArtifactAlreadyExistsError(AlreadyExistsError):
    code = "JOB_FRAME_ARTIFACT_ALREADY_EXISTS"

    def __init__(self, job_run_num: int, job_def_id: int, route_id: str, frame_pk: int, role: ArtifactRole) -> None:
        super().__init__(
            f"Job frame artifact with role {role} for frame {frame_pk} and job run {(job_run_num, job_def_id, route_id)} already exists",
            context={**_job_run_context(job_run_num, job_def_id, route_id), "frame_pk": frame_pk, "role": role},
        )


class JobFrameArtifactNotFoundError(NotFoundError):
    code = "JOB_FRAME_ARTIFACT_NOT_FOUND"
    hint = _MISSING_FILE_HINT

    def __init__(self, job_run_num: int, job_def_id: int, route_id: str, frame_pk: int, role: ArtifactRole) -> None:
        super().__init__(
            f"Job frame artifact with role {role} for frame {frame_pk} and job run {(job_run_num, job_def_id, route_id)} not found",
            context={**_job_run_context(job_run_num, job_def_id, route_id), "frame_pk": frame_pk, "role": role},
        )


# ─── Job segment runs & CVAT imports ─────────────────────────────────────────

def _job_segment_run_context(job_run_num: int, job_def_id: int, route_id: str, segment_id: int) -> dict[str, Any]:
    return {**_job_run_context(job_run_num, job_def_id, route_id), "segment_id": segment_id}


class JobSegmentRunAlreadyExistsError(AlreadyExistsError):
    code = "JOB_SEGMENT_RUN_ALREADY_EXISTS"

    def __init__(self, job_run_num: int, job_def_id: int, route_id: str, segment_id: int) -> None:
        super().__init__(
            f"Job segment run {(job_run_num, job_def_id, route_id, segment_id)} already exists",
            context=_job_segment_run_context(job_run_num, job_def_id, route_id, segment_id),
        )


class JobSegmentRunNotFoundError(NotFoundError):
    code = "JOB_SEGMENT_RUN_NOT_FOUND"
    hint = (
        "This job run has no result for the segment. The job may still be running, or "
        "the segment failed during the job; check the job run's segment statuses."
    )

    def __init__(self, job_run_num: int, job_def_id: int, route_id: str, segment_id: int) -> None:
        super().__init__(
            f"Job segment run {(job_run_num, job_def_id, route_id, segment_id)} not found",
            context=_job_segment_run_context(job_run_num, job_def_id, route_id, segment_id),
        )


class JobSegmentRunReviewNotFound(NotFoundError):
    code = "CVAT_IMPORT_NOT_FOUND"
    hint = "This segment has not been sent to CVAT yet. Use the CVAT button on the segment to import it."

    def __init__(
        self,
        job_run_num: int,
        job_def_id: int,
        route_id: str,
        segment_id: int,
    ) -> None:
        super().__init__(
            f"Job segment run review {(job_run_num, job_def_id, route_id, segment_id)} not found",
            context=_job_segment_run_context(job_run_num, job_def_id, route_id, segment_id),
        )


class JobSegmentRunImportDeleteError(ConflictError):
    code = "CVAT_IMPORT_BUSY"
    hint = (
        "A CVAT import is still loading or being removed. Wait until it shows LOADED, "
        "REMOVED or FAILED, then try again."
    )

    def __init__(self, reason: str):
        super().__init__(reason)


# ─── CVAT server ─────────────────────────────────────────────────────────────

class CVATActiveError(ConflictError):
    code = "CVAT_BUSY"
    hint = "Wait for running job runs and in-progress CVAT imports to finish, then restart CVAT."

    def __init__(self) -> None:
        super().__init__("Cannot restart CVAT while job runs or CVAT imports are active.")


class CVATUnavailableError(PipelineError, RuntimeError):
    """CVAT could not be reached or did not authenticate.

    Also a RuntimeError so existing ``except RuntimeError`` callers keep working.
    """

    code = "CVAT_UNAVAILABLE"
    status_code = HTTP_503_SERVICE_UNAVAILABLE
    hint = (
        "Make sure the CVAT containers are running (./scripts/setup_cvat.sh) and that "
        "CVAT_EMAIL / CVAT_PASSWORD in your .env match a CVAT user. CVAT can take a "
        "minute to come up after a restart."
    )

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CVATRestartError(PipelineError):
    code = "CVAT_RESTART_FAILED"
    status_code = HTTP_503_SERVICE_UNAVAILABLE
    hint = (
        "The backend could not restart the cvat_server container. Check that Docker is "
        "running, the cvat_server container exists (docker ps -a), and "
        "/var/run/docker.sock is mounted into the backend container."
    )

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ─── comma.ai (openpilot) API ────────────────────────────────────────────────

class InvalidRouteIdError(PipelineError):
    code = "INVALID_ROUTE_ID"
    status_code = HTTP_400_BAD_REQUEST
    hint = "Route IDs look like <dongle_id>|<log_id>, e.g. db478799b6f9f210|0000000e--9ecd39f6bc."

    def __init__(self, route_id: str) -> None:
        super().__init__(f"'{route_id}' is not a valid route ID", context={"route_id": route_id})


class CommaAuthError(PipelineError):
    code = "COMMA_AUTH_FAILED"
    status_code = HTTP_503_SERVICE_UNAVAILABLE
    hint = (
        "COMMA_JWT in your .env is missing, expired, or has no access to this device. Get a new "
        "token from https://jwt.comma.ai, update .env, and rebuild the open_pilot_download_worker."
    )

    def __init__(self, dongle_id: str, http_status: int) -> None:
        super().__init__(
            f"comma.ai rejected the request for device {dongle_id} (HTTP {http_status})",
            context={"dongle_id": dongle_id, "http_status": http_status},
        )


class CommaApiError(PipelineError):
    code = "COMMA_API_ERROR"
    status_code = HTTP_503_SERVICE_UNAVAILABLE
    hint = "The comma.ai API is unreachable or returned an error. Check your internet connection and retry later."

    def __init__(self, message: str, dongle_id: str) -> None:
        super().__init__(message, context={"dongle_id": dongle_id})


class CommaRouteNotFoundError(NotFoundError):
    code = "COMMA_ROUTE_NOT_FOUND"
    hint = (
        "The device exists but has no route with this ID. Check for typos, and check on "
        "https://connect.comma.ai that the route is still there and fully uploaded."
    )

    def __init__(self, route_id: str) -> None:
        super().__init__(f"Route {route_id} was not found on comma.ai", context={"route_id": route_id})


class RouteHasNoSegmentsError(ConflictError):
    code = "ROUTE_HAS_NO_SEGMENTS"
    hint = (
        "The route has no segments to process. It may not have finished downloading, or every "
        "segment failed to download; check the route page, then delete and re-import the route."
    )

    def __init__(self, route_id: str) -> None:
        super().__init__(f"Route {route_id} has no segments to process", context={"route_id": route_id})


# ─── Audit log ───────────────────────────────────────────────────────────────

class InvalidAuditFilterError(PipelineError):
    code = "INVALID_AUDIT_FILTER"
    status_code = HTTP_400_BAD_REQUEST
    hint = "outcome must be one of: success, warning, failure."

    def __init__(self, message: str) -> None:
        super().__init__(message)
