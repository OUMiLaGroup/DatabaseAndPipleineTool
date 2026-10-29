from contextlib import asynccontextmanager
import os
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine

from db.url import build_database_url
from api.request_context import (
    REQUEST_ID_HEADER,
    configure_api_logging,
    get_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)
from services.errors import PipelineError
from services.audit_service import AuditService
from api.audit import (
    AUDITED_METHODS,
    NOT_AUDITED_PATH_PREFIXES,
    buffer_response,
    read_request_ids,
    record_api_action,
)

from api.routers.dataset_exports import dataset_exports_router
from api.routers.routes import routes_router
from api.routers.segments import segments_router
from api.routers.job_runs import job_runs_router
from api.routers.job_definitions import job_definitions_router
from api.routers.job_segment_run import job_segment_run_router
from api.routers.cvat import cvat_router
from api.routers.audit_logs import audit_logs_router

configure_api_logging()
logger = logging.getLogger("api")

FRONTEND_URL = os.getenv("FRONTEND_URL")
if not FRONTEND_URL:
    raise ValueError("FRONTEND_URL can not be empty")

@asynccontextmanager
async def lifespan(app: FastAPI):
    
    engine: AsyncEngine = create_async_engine(build_database_url(), pool_pre_ping=True)
    session_local: async_sessionmaker[AsyncSession] = async_sessionmaker(bind=engine, expire_on_commit=False)

    app.state.engine = engine
    app.state.session_local = session_local 
    # Audit entries are written in their own session so they survive a rolled-back request
    app.state.audit_service = AuditService(session_local, source="api")

    try:
        yield
    finally:
        await engine.dispose()

app = FastAPI(lifespan=lifespan)


# ─── Error reporting ──────────────────────────────────────────────────────────
# Every error response has the same shape so the frontend can show it clearly:
#   {"detail": str, "code": str, "hint": str | None, "context": dict, "request_id": str}
# See services/errors.py for the list of error codes.

INTERNAL_ERROR_HINT = (
    "This is a bug or an infrastructure problem (database, MinIO or CVAT down). "
    "Check the backend logs for this request: docker compose logs backend | grep {request_id}"
)


def _error_response(status_code: int, body: dict) -> JSONResponse:
    request_id = get_request_id()
    return JSONResponse(
        status_code=status_code,
        content={**body, "request_id": request_id},
        headers={REQUEST_ID_HEADER: request_id},
    )


async def request_context_middleware(request: Request, call_next):
    """Assigns a request ID and turns any unhandled exception into a JSON 500.

    Registered *before* CORSMiddleware so it sits inside it: that way even 500
    responses get CORS headers and the browser can read the error body.
    """
    request_id = new_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = set_request_id(request_id)
    audited = request.method in AUDITED_METHODS and not request.url.path.startswith(NOT_AUDITED_PATH_PREFIXES)
    request_ids = await read_request_ids(request) if audited else {}
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            response = _error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                {
                    "detail": "An unexpected error occurred on the server.",
                    "code": "INTERNAL_ERROR",
                    "hint": INTERNAL_ERROR_HINT.format(request_id=request_id),
                    "context": {"method": request.method, "path": request.url.path},
                },
            )
        response.headers[REQUEST_ID_HEADER] = request_id

        # Record every change request (successful or not) in the audit log
        audit_service: AuditService | None = getattr(request.app.state, "audit_service", None)
        if audited and audit_service is not None:
            try:
                response, body = await buffer_response(response)
                await record_api_action(audit_service, request, request_ids, response.status_code, body, request_id)
            except Exception:
                logger.exception("Audit logging failed for %s %s", request.method, request.url.path)
        return response
    finally:
        reset_request_id(token)


app.middleware("http")(request_context_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)


@app.exception_handler(PipelineError)
async def handle_pipeline_error(request: Request, exc: PipelineError) -> JSONResponse:
    # Expected errors (not found, conflict, validation) are logged without a traceback
    logger.warning(
        "%s %s -> %s %s: %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.code,
        exc.message,
    )
    return _error_response(exc.status_code, exc.to_dict())


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Turn pydantic's error list into one readable sentence, keep the raw list in "errors"
    problems = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err.get("loc", ()) if part != "body")
        problems.append(f"{location}: {err.get('msg')}" if location else str(err.get("msg")))
    logger.warning("%s %s -> 422 VALIDATION_ERROR: %s", request.method, request.url.path, problems)
    return _error_response(
        422,  # literal: the constant's name differs between Starlette versions
        {
            "detail": "Invalid request: " + "; ".join(problems),
            "code": "VALIDATION_ERROR",
            "hint": "Fix the fields listed above (missing values or wrong types), then try again.",
            "context": {},
            "errors": jsonable_encoder(exc.errors()),
        },
    )

@app.get("/health-check")
async def health_check() -> dict[str, str]:
    return {"status": "alive"}


app.include_router(router=routes_router)
app.include_router(router=segments_router)
app.include_router(router=job_runs_router)
app.include_router(router=job_definitions_router)
app.include_router(router=job_segment_run_router)
app.include_router(router=dataset_exports_router)
app.include_router(router=cvat_router)
app.include_router(router=audit_logs_router)
