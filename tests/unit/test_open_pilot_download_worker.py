from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from db.enums import SegmentStatus
from services.route_service import RouteStatus
from open_pilot_download_worker.main import process_route


@pytest.mark.asyncio
async def test_process_route_moves_successful_route_to_upload_queue():
    """
    Verify the OpenPilot Download Worker moves a successfully processed route
    through the expected download lifecycle without using real external
    services, processes, or database connections.
    """
    route_id = "db478799b6f9f210|00000044--2b2126c478"

    route = SimpleNamespace(route_id=route_id)
    segment = SimpleNamespace(route_id=route_id, segment_id=0)

    route_service = AsyncMock()
    segment_service = AsyncMock()
    session = AsyncMock()

    mock_create_segments = AsyncMock(return_value=[segment])
    mock_extract_segment = AsyncMock()

    with (
        patch(
            "open_pilot_download_worker.main.create_segments_for_route",
            new=mock_create_segments,
        ),
        patch(
            "open_pilot_download_worker.main._extract_single_segment",
            new=mock_extract_segment,
        ),
    ):
        await process_route(
            route_to_process=route,
            route_service=route_service,
            segment_service=segment_service,
            session=session,
        )

    # The route should enter DOWNLOADING and finish in UPLOAD_QUEUE.
    assert route_service.set_status.await_args_list == [
        call(route_id=route_id, status=RouteStatus.DOWNLOADING),
        call(route_id=route_id, status=RouteStatus.UPLOAD_QUEUE),
    ]

    # The segment should follow the same successful lifecycle.
    assert segment_service.set_status.await_args_list == [
        call(
            route_id=route_id,
            segment_id=0,
            status=SegmentStatus.DOWNLOADING,
        ),
        call(
            route_id=route_id,
            segment_id=0,
            status=SegmentStatus.UPLOAD_QUEUE,
        ),
    ]

    # Confirm the worker delegated segment creation and extraction.
    mock_create_segments.assert_awaited_once_with(route, segment_service)
    mock_extract_segment.assert_awaited_once()

    # A generated storage path should be assigned to the route.
    route_service.set_file_path.assert_awaited_once()
