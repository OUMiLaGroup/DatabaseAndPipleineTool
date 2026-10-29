import asyncio
import os
import shlex
import signal
from pathlib import Path
from uuid import uuid4
import shutil

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.enums import SegmentStatus
from db.models.route import Route
from db.models.segment import Segment
from db.url import build_database_url
from repositories.route_repository import RouteRepository
from repositories.segment_repository import SegmentRepository
from services.open_pilot_route_service import OpenPilotRouteService
from services.route_service import RouteService, RouteStatus
from services.segment_service import SegmentService
from utilities.timing_utilities import convert_milliseconds_to_timestamp
from utilities.download_errors import describe_download_failure


POLL_INTERVAL_SECONDS = 2.0
OPENPILOT_DIR = Path("/app/openpilot")
DATA_ROOT = Path("/app/data")
ROUTE_PROCESS_TIMEOUT_SECONDS = float(os.getenv("ROUTE_PROCESS_TIMEOUT_SECONDS", "0"))

logger = configure_logging("open_pilot_download_worker")


def _output_dir_snapshot(output_dir: Path, *, sample_limit: int = 10) -> tuple[int, list[str]]:
    if not output_dir.exists():
        return 0, []

    files: list[str] = []
    total = 0
    for item in output_dir.rglob("*"):
        if item.is_file():
            total += 1
            if len(files) < sample_limit:
                files.append(str(item.relative_to(output_dir)))
    return total, files


def _build_openpilot_bash(inner_command: str) -> str:
    conda_env_name = os.getenv("CONDA_ENV_NAME", "openpilot")
    quoted_conda_env = shlex.quote(conda_env_name)
    return (
        "set -euo pipefail\n"
        "export TERM=xterm\n"
        "source ~/miniconda3/etc/profile.d/conda.sh\n"
        f"conda activate {quoted_conda_env}\n"
        f"cd {shlex.quote(str(OPENPILOT_DIR))}\n"
        "source ./.venv/bin/activate\n"
        f"{inner_command}"
    )


async def _start_extraction_process(output_dir: Path) -> asyncio.subprocess.Process:
    command = _build_openpilot_bash(
        "python ./selfdrive/modeld/extract_data.py --output_dir "
        f"{shlex.quote(str(output_dir))}"
    )
    return await asyncio.create_subprocess_exec(
        "bash",
        "-lc",
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        preexec_fn=os.setsid,
    )


async def _start_replay_process(route_id: str) -> asyncio.subprocess.Process:
    replay_command = f"./tools/replay/replay {shlex.quote(route_id)} --all --ecam"
    command = _build_openpilot_bash(
        f"script -q -e -f -c {shlex.quote(replay_command)} /dev/null"
    )
    return await asyncio.create_subprocess_exec(
        "bash",
        "-lc",
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        preexec_fn=os.setsid,
    )


async def _stream_process_output(
    process: asyncio.subprocess.Process,
    process_name: str,
    route_id: str,
    log: bool = True
) -> None:
    if process.stdout is None:
        return

    chunk_size = 4096
    max_partial_line = 64 * 1024
    buffer = ""

    while True:
        raw = await process.stdout.read(chunk_size)
        if not raw:
            break

        buffer += raw.decode(errors="replace")

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if process_name == 'replay' and len(line) > 500:
                continue  # Replay's interactive terminal redraws are not useful log lines.
            if log:
                logger.info("[%s] route=%s %s", process_name, route_id, line.rstrip("\r"))

        if len(buffer) > max_partial_line:
            if log and process_name != 'replay':
                logger.info(
                    "[%s] route=%s %s ... [long line truncated]",
                    process_name,
                    route_id,
                    buffer[:1024].rstrip("\r"),
                )
            buffer = ""

    if buffer and not (process_name == 'replay' and len(buffer) > 500):
        if log:
            logger.info("[%s] route=%s %s", process_name, route_id, buffer.rstrip("\r"))


async def _force_stop_process(process: asyncio.subprocess.Process | None) -> None:
    if process is None or process.returncode is not None:
        return

    try:
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except Exception:
        process.kill()

    try:
        await asyncio.wait_for(process.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pass


async def _mark_stale_downloading_routes_as_failed(route_service: RouteService) -> None:
    stale_routes = await route_service.get_routes_by_status(status=RouteStatus.DOWNLOADING)
    if not stale_routes:
        return

    for route in stale_routes:
        await route_service.set_status(route.route_id, RouteStatus.FAILED)
        await route_service.set_download_error(route.route_id, {'code': 'interrupted', 'message': 'The download worker stopped before this route finished. Restart the services and retry the route.'})
        if route.file_path:
            shutil.rmtree(DATA_ROOT / str(route.file_path), ignore_errors=True)
        logger.warning("Marked stale route as failed on startup: route=%s", route.route_id)
        await record_audit(
            "route.download.interrupted",
            OUTCOME_FAILURE,
            entity_type="route",
            entity_id=route.route_id,
            route_id=route.route_id,
            message="The open_pilot_download_worker restarted while this route was downloading.",
        )


async def _extract_single_segment(segment_path: str, output_dir: Path) -> None:
    """
    Extract a single segment: orchestrate replay and extraction processes.

    Raises RuntimeError on timeout, replay early exit, or extraction failure.
    """
    extraction_process: asyncio.subprocess.Process | None = None
    replay_process: asyncio.subprocess.Process | None = None
    extraction_stream_task: asyncio.Task[None] | None = None
    replay_stream_task: asyncio.Task[None] | None = None
    extraction_exit_code: int | None = None
    extraction_wait_task: asyncio.Task[int] | None = None
    replay_wait_task: asyncio.Task[int] | None = None

    try:
        extraction_process = await _start_extraction_process(output_dir)
        logger.info(
            "Started extraction for route=%s pid=%s",
            segment_path,
            extraction_process.pid,
        )
        extraction_stream_task = asyncio.create_task(
            _stream_process_output(extraction_process, "extract", segment_path)
        )

        replay_process = await _start_replay_process(segment_path)
        logger.info(
            "Started replay for route=%s pid=%s",
            segment_path,
            replay_process.pid,
        )
        replay_stream_task = asyncio.create_task(
            _stream_process_output(replay_process, "replay", segment_path)
        )

        extraction_wait_task = asyncio.create_task(extraction_process.wait())
        replay_wait_task = asyncio.create_task(replay_process.wait())

        route_start_time = asyncio.get_running_loop().time()
        while True:
            done, _ = await asyncio.wait(
                {extraction_wait_task, replay_wait_task},
                timeout=1.0,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if ROUTE_PROCESS_TIMEOUT_SECONDS > 0:
                elapsed = asyncio.get_running_loop().time() - route_start_time
                if elapsed > ROUTE_PROCESS_TIMEOUT_SECONDS:
                    raise RuntimeError(
                        f"route processing exceeded timeout ({ROUTE_PROCESS_TIMEOUT_SECONDS}s) "
                        f"for route {segment_path}"
                    )

            if replay_wait_task in done and not extraction_wait_task.done():
                replay_exit_code = replay_wait_task.result()
                raise RuntimeError(
                    f"replay exited early with code {replay_exit_code} "
                    f"while extraction still running for route {segment_path}"
                )

            if extraction_wait_task in done:
                extraction_exit_code = extraction_wait_task.result()
                break

        logger.info(
            "Extraction exited for route=%s code=%s",
            segment_path,
            extraction_exit_code,
        )
        if extraction_exit_code != 0:
            raise RuntimeError(
                f"extraction exited with code {extraction_exit_code} "
                f"for route {segment_path}"
            )
    finally:
        await _force_stop_process(replay_process)
        await _force_stop_process(extraction_process)

        if extraction_wait_task is not None and not extraction_wait_task.done():
            extraction_wait_task.cancel()
        if replay_wait_task is not None and not replay_wait_task.done():
            replay_wait_task.cancel()

        if extraction_stream_task is not None:
            await extraction_stream_task
        if replay_stream_task is not None:
            await replay_stream_task


async def create_segments_for_route(route: Route, segment_service: SegmentService) -> list[Segment]:
    open_pilot_route_service = OpenPilotRouteService()
    await open_pilot_route_service.require_downloadable_files(route.route_id)
    route_metadata = await open_pilot_route_service.get_route_metadata(route_name=route.route_id)

    if not route_metadata:
        raise CommaRouteNotFoundError(route.route_id)

    num_segments = len(route_metadata.segment_numbers)

    segments: list[Segment] = []
    for segment_index in range(num_segments):
        segment = await segment_service.create_segment(
            route_id=route.route_id,
            segment_id=route_metadata.segment_numbers[segment_index],
            start_time=convert_milliseconds_to_timestamp(route_metadata.segment_start_times[segment_index]),
            end_time=convert_milliseconds_to_timestamp(route_metadata.segment_end_times[segment_index]),
            status=SegmentStatus.DOWNLOAD_QUEUE
        )
        segments.append(segment)

    return segments


async def process_route(route_to_process: Route, route_service: RouteService, segment_service: SegmentService, session: AsyncSession):
    logging.info(f"Processing route {route_to_process.route_id}")
    await route_service.set_download_error(route_to_process.route_id, None)
    await route_service.set_status(
        route_id=route_to_process.route_id,
        status=RouteStatus.DOWNLOADING
    )
    await session.commit()

    unique_path = str(uuid4())
    data_dir = DATA_ROOT / unique_path
    failed_segments = 0
    try:
        await route_service.set_status(route_id=route_id, status=RouteStatus.DOWNLOADING)
        await session.commit()

        segments_to_download: list[Segment] = await create_segments_for_route(
            route_to_process,
            segment_service
        )
        segment_ids = [segment.segment_id for segment in segments_to_download]
        await session.commit()
        logger.info("Found %d segments for %s", len(segment_ids), route_id)
        if not segment_ids:
            raise RouteHasNoSegmentsError(route_id)

        await route_service.set_file_path(route_id=route_id, file_path=unique_path)
        await session.commit()

        # Download every segment; a failed segment is recorded and skipped
        failures: dict[int, str | None] = {}
        for segment_id in segment_ids:
            await segment_service.set_status(
                route_id=route_id,
                segment_id=segment_id,
                status=SegmentStatus.DOWNLOADING
            )
            await session.commit()

            try:
                await _extract_single_segment(
                    # should look like this: "db478799b6f9f210/00000040--8afe968813/1"
                    segment_path=f"{route_id}/{segment_id}",
                    output_dir=data_dir / str(segment_id)
                )
                await segment_service.set_status(
                    route_id=route_id,
                    segment_id=segment_id,
                    status=SegmentStatus.UPLOAD_QUEUE
                )
                await session.commit()
                logging.info(f"Successfully uploaded segment {segment}")
            except Exception as error:
                failed_segments += 1
                details = describe_download_failure(error)
                details['message'] = f"Segment {segment.segment_id}: " + details['message']
                await route_service.set_download_error(route_to_process.route_id, details)
                logging.exception("Failed to download segment %s; continuing with the next segment", segment)
                shutil.rmtree(data_dir / str(segment.segment_id), ignore_errors=True)
                await segment_service.set_status(
                    route_id=segment.route_id,
                    segment_id=segment.segment_id,
                    status=SegmentStatus.FAILED
                )
                shutil.rmtree(data_dir / str(segment_id), ignore_errors=True)
                await record_failure(
                    session,
                    logger,
                    f"segment {route_id}/{segment_id}",
                    lambda: segment_service.set_status(
                        route_id=route_id,
                        segment_id=segment_id,
                        status=SegmentStatus.FAILED,
                        error=error,
                    ),
                )

        if len(failures) == len(segment_ids):
            # Nothing to upload. Before this fix the route went to UPLOAD_QUEUE and stayed there forever.
            shutil.rmtree(data_dir, ignore_errors=True)
            error = summarize_segment_failures(failures, len(segment_ids), action="failed to download")
            logger.error("Every segment of route %s failed to download", route_id)
            await route_service.set_status(route_id=route_id, status=RouteStatus.FAILED, error=error)
            await session.commit()
            await record_audit(
                "route.download.finished", OUTCOME_FAILURE,
                entity_type="route", entity_id=route_id, route_id=route_id, message=error,
                details={"segments_total": len(segment_ids), "segments_failed": len(failures)},
            )
        else:
            if failures:
                # Some segments failed: keep going with the rest, but record a warning on the route
                warning = summarize_segment_failures(failures, len(segment_ids), action="failed to download")
                await route_service.set_status(route_id=route_id, status=RouteStatus.UPLOAD_QUEUE, error=warning)
            else:
                await route_service.set_status(route_id=route_id, status=RouteStatus.UPLOAD_QUEUE)
            logger.info("Route %s downloaded (%d failed segment(s))", route_id, len(failures))
            await session.commit()
            await record_audit(
                "route.download.finished", OUTCOME_WARNING if failures else OUTCOME_SUCCESS,
                entity_type="route", entity_id=route_id, route_id=route_id,
                message=warning if failures else None,
                details={"segments_total": len(segment_ids), "segments_failed": len(failures)},
            )

    except Exception as e:
        await route_service.set_download_error(route_to_process.route_id, describe_download_failure(e))
        await route_service.set_status(
            route_id=route_to_process.route_id,
            status=RouteStatus.FAILED
        )
        await session.commit()
        logging.exception("Could not process route %s", route_to_process.route_id)
        shutil.rmtree(data_dir, ignore_errors=True)
        return

    logging.info(f"Rout processed {route_to_process.route_id}")
    await route_service.set_status(
        route_id=route_to_process.route_id,
        status=RouteStatus.FAILED if failed_segments else RouteStatus.UPLOAD_QUEUE
    )
    await session.commit()
    


async def main():
    engine = create_async_engine(build_database_url(), pool_pre_ping=True)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    configure_audit(SessionLocal, source="open_pilot_download_worker")
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        async with SessionLocal() as session:
            route_repository = RouteRepository(session=session)
            route_service = RouteService(route_repository=route_repository)
            segment_repository = SegmentRepository(session=session)
            segment_service = SegmentService(segment_repository=segment_repository)

            await _mark_stale_downloading_routes_as_failed(route_service)
            await session.commit()

            while not stop_event.is_set():
                logger.info("Checking for new segment")
                route_to_process = await route_service.get_next_route_by_status(
                    status=RouteStatus.DOWNLOAD_QUEUE
                )
                if route_to_process is None:
                    await session.rollback()
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                await process_route(
                    route_to_process=route_to_process,
                    route_service=route_service,
                    segment_service=segment_service,
                    session=session
                )

            logger.info("Stop event received, shutting down worker")
    finally:
        await engine.dispose()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
