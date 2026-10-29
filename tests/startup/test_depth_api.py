"""Run in backend; no database writes or model downloads."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from db.enums import CameraType, JobType
from schemas.job_definition import CreateJobDefinitionRequest
from api.routers import job_runs, job_segment_run


class DepthApiTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_model_and_resolution_are_rejected(self):
        for config in ({"process_res": 1}, {"model_name": "relative-model"}, {"calibrations": {"front_regular": {"width": 1928, "height": 1208, "fx": -1, "fy": 1}}}):
            with self.assertRaises(ValueError):
                CreateJobDefinitionRequest(type="depth", implementation_key="depth_anything_3", name="test", config=config)

    async def test_missing_required_calibration_fails_before_queuing(self):
        definition = SimpleNamespace(type=JobType.DEPTH, config={"require_metric": True})
        definitions = SimpleNamespace(get_job_definition=AsyncMock(return_value=definition))
        payload = SimpleNamespace(job_def_id=2, route_id="test", camera=CameraType.FRONT_REGULAR)
        with patch.object(job_runs, "build_job_definition_service", return_value=definitions):
            with self.assertRaises(HTTPException) as error:
                await job_runs.create_job_run(payload, AsyncMock())
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("calibration", error.exception.detail)

    async def test_dense_depth_cannot_be_queued_for_cvat_box_import(self):
        definition = SimpleNamespace(type=JobType.DEPTH)
        definitions = SimpleNamespace(get_job_definition=AsyncMock(return_value=definition))
        with patch.object(job_segment_run, "build_job_definition_service", return_value=definitions):
            with self.assertRaises(HTTPException) as error:
                await job_segment_run.import_job_segment_run_to_cvat("test", 2, 1, 0, CameraType.FRONT_REGULAR, AsyncMock())
        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("NPZ", error.exception.detail)


if __name__ == "__main__":
    unittest.main()
