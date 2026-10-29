import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from services.dataset_export_service import DatasetExportService
from services.errors import DatasetExportValidationError
from db.enums import CameraType, JobStatus, RouteStatus, JobSegmentRunStatus


class ExportReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def check_segments(self, rows, blocked):
        exports, selected, routes, jobs, frames, artifacts = [AsyncMock() for _ in range(6)]
        routes.get_by_id.return_value = SimpleNamespace(status=RouteStatus.UPLOADED)
        jobs.get_by_id.return_value = SimpleNamespace(status=JobStatus.SUCCEEDED)
        jobs.get_segments_for_export.return_value = rows
        exports.create.return_value = SimpleNamespace(export_id=99)
        service = DatasetExportService(exports, selected, routes, jobs, frames, artifacts)
        with patch.object(service, '_validate_camera_views_exist_on_route', AsyncMock()):
            args = dict(route_id='demo', camera_views=[CameraType.FRONT_REGULAR], job_runs=[(1, 1, CameraType.FRONT_REGULAR)])
            if blocked:
                with self.assertRaisesRegex(DatasetExportValidationError, 'incomplete'):
                    await service.create_dataset_export(**args)
                exports.create.assert_not_awaited()
            else:
                await service.create_dataset_export(**args)
                exports.create.assert_awaited_once()

    async def test_false_success_with_missing_segment_output_is_blocked(self):
        await self.check_segments([SimpleNamespace(segment_id=2, status=JobSegmentRunStatus.FAILED, artifact_id=None)], True)

    async def test_complete_annotation_can_be_exported(self):
        await self.check_segments([SimpleNamespace(segment_id=2, status=JobSegmentRunStatus.SUCCEEDED, artifact_id='stored')], False)


if __name__ == '__main__':
    unittest.main()
