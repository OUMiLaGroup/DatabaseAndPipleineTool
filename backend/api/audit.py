"""
Records every change made through the API in the audit log (see services/audit_service.py).

Called from the request middleware in main.py for POST/PUT/PATCH/DELETE requests, after the
response is known, so failed attempts are recorded too, with the error code the user saw.
The action name and the IDs involved are worked out from the endpoint that handled the request,
its path/query parameters, the JSON request body and the JSON response body.
"""
import json
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from services.audit_service import OUTCOME_FAILURE, OUTCOME_SUCCESS, AuditService, entity_id_for

logger = logging.getLogger(__name__)

AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
NOT_AUDITED_PATH_PREFIXES = ("/audit-logs",)

# Endpoint function name -> (action, entity type)
API_ACTIONS: dict[str, tuple[str, str]] = {
    "create_route": ("route.import", "route"),
    "delete_route": ("route.delete", "route"),
    "create_job_definition": ("job_definition.create", "job_definition"),
    "delete_job_definition": ("job_definition.delete", "job_definition"),
    "create_job_run": ("job_run.create", "job_run"),
    "cancel_job_run": ("job_run.cancel", "job_run"),
    "requeue_job_run": ("job_run.requeue", "job_run"),
    "delete_job_run": ("job_run.delete", "job_run"),
    "import_job_segment_run_to_cvat": ("cvat.load_segment", "cvat_import"),
    "delete_job_segment_run_in_cvat": ("cvat.remove_segment", "cvat_import"),
    "create_dataset_export": ("dataset_export.create", "dataset_export"),
    "delete_dataset_export": ("dataset_export.delete", "dataset_export"),
    "restart_cvat_server": ("cvat.restart", "cvat_server"),
}

ID_FIELDS = ("route_id", "job_def_id", "job_run_num", "camera", "segment_id", "export_id")


def _pick_ids(source: Any, into: dict[str, Any]) -> None:
    if isinstance(source, dict):
        for key in ID_FIELDS:
            if key in source and source[key] is not None and key not in into:
                into[key] = source[key]


async def read_request_ids(request: Request) -> dict[str, Any]:
    """IDs from query parameters and a JSON body. Call before the request is handled."""
    ids: dict[str, Any] = {}
    _pick_ids(dict(request.query_params), ids)
    if "application/json" in request.headers.get("content-type", ""):
        try:
            _pick_ids(json.loads(await request.body() or b"null"), ids)
        except Exception:
            pass  # unreadable body: the audit entry just has fewer IDs
    return ids


async def buffer_response(response: Response) -> tuple[Response, bytes]:
    """Read a response body so it can be inspected, and return an equivalent response."""
    if not hasattr(response, "body_iterator"):
        # Already a plain response (e.g. the JSON 500 built in main.py): body is in memory
        return response, bytes(getattr(response, "body", b"") or b"")
    body = b""
    async for chunk in response.body_iterator:  # type: ignore[attr-defined]
        body += chunk if isinstance(chunk, bytes) else chunk.encode()
    rebuilt = Response(
        content=body,
        status_code=response.status_code,
        headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
        media_type=response.media_type,
        background=getattr(response, "background", None),
    )
    return rebuilt, body


async def record_api_action(
    audit_service: AuditService,
    request: Request,
    request_ids: dict[str, Any],
    status_code: int,
    response_body: bytes,
    request_id: str,
) -> None:
    """Write one audit entry for a finished change request. Never raises."""
    try:
        endpoint = request.scope.get("endpoint")
        endpoint_name = getattr(endpoint, "__name__", None)
        action, entity_type = API_ACTIONS.get(
            endpoint_name or "",
            (f"api.{request.method.lower()} {request.url.path}", None),
        )

        ids = dict(request_ids)
        _pick_ids(request.scope.get("path_params") or {}, ids)

        try:
            body = json.loads(response_body) if response_body else None
        except ValueError:
            body = None

        failed = status_code >= 400
        message = None
        error_code = None
        if failed and isinstance(body, dict):
            message = body.get("detail") if isinstance(body.get("detail"), str) else None
            error_code = body.get("code")
            _pick_ids(body.get("context"), ids)
        elif not failed:
            _pick_ids(body, ids)  # e.g. the new job_run_num or export_id

        if failed and message is None:
            message = f"HTTP {status_code}"

        await audit_service.record(
            action,
            OUTCOME_FAILURE if failed else OUTCOME_SUCCESS,
            entity_type=entity_type,
            entity_id=entity_id_for(entity_type, ids),
            route_id=str(ids["route_id"]) if ids.get("route_id") is not None else None,
            message=message,
            error_code=error_code,
            request_id=request_id,
            details={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                **{k: v for k, v in ids.items() if isinstance(v, (str, int, float, bool))},
            },
        )
    except Exception:
        logger.exception("Could not record audit entry for %s %s", request.method, request.url.path)
