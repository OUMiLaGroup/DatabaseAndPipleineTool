"""Run inside the download-worker image: python /verification.py."""
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from unittest.mock import Mock

sys.path.insert(0, '/app/src')
import main
from services.open_pilot_route_service import OpenPilotRouteService
from services.route_service import RouteService
from utilities.download_errors import MissingRouteRecordingsError


class DownloadFailureTests(unittest.IsolatedAsyncioTestCase):
    async def check_failure(self, metadata_error=False):
        route = SimpleNamespace(route_id='db478799b6f9f210|00000081--23c1159034')
        segment = SimpleNamespace(route_id=route.route_id, segment_id=0)
        routes, segments, session = AsyncMock(), AsyncMock(), AsyncMock()
        metadata = AsyncMock(side_effect=MissingRouteRecordingsError('no recordings')) if metadata_error else AsyncMock(return_value=[segment])
        with patch.object(main, 'create_segments_for_route', metadata), patch.object(main, '_extract_single_segment', AsyncMock(side_effect=RuntimeError('replay failed'))):
            await main.process_route(route, routes, segments, session)
        self.assertEqual(routes.set_status.await_args_list[-1].kwargs['status'], main.RouteStatus.FAILED)
        details = routes.set_download_error.await_args_list[-1].args[1]
        self.assertEqual(details['code'], 'recordings_unavailable' if metadata_error else 'processing_failed')
        self.assertTrue(details['message'])
        self.assertNotIn(main.RouteStatus.UPLOAD_QUEUE, [c.kwargs['status'] for c in routes.set_status.await_args_list])
        if not metadata_error:
            self.assertEqual(segments.set_status.await_args_list[-1].kwargs['status'], main.SegmentStatus.FAILED)

    async def test_missing_recordings_does_not_queue_upload_or_crash(self):
        await self.check_failure(metadata_error=True)

    async def test_missing_output_after_replay_failure_does_not_crash(self):
        await self.check_failure()

    async def test_metadata_with_no_files_is_rejected_before_replay(self):
        client = AsyncMock()
        client.get.return_value = Mock(json=Mock(return_value={'logs': [], 'cameras': [], 'ecameras': []}))
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch('services.open_pilot_route_service.httpx.AsyncClient', return_value=context):
            with self.assertRaisesRegex(ValueError, 'no complete downloadable'):
                await OpenPilotRouteService().require_downloadable_files('demo|route')

    async def test_slash_input_is_normalized_before_duplicate_check(self):
        repository = AsyncMock()
        repository.get_by_id.return_value = None
        route_id = 'db478799b6f9f210|0000000e--9ecd39f6bc'
        await RouteService(repository).create_route(route_id.replace('|', '/'))
        repository.get_by_id.assert_awaited_once_with(route_id)
        self.assertEqual(repository.create.await_args.kwargs['route_id'], route_id)


if __name__ == '__main__':
    unittest.main()
