"""Run in cvat_worker: python /verification.py."""
import sys
sys.path.insert(0, '/app')
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import main as worker


class CompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_segment_cannot_mark_job_succeeded(self):
        job = SimpleNamespace(job_run_num=1, job_def_id=1, route_id='demo', camera='front_regular')
        row = SimpleNamespace(segment_id=2, status=worker.JobSegmentRunStatus.FAILED, artifact_id=None)
        definitions, jobs, session = AsyncMock(), AsyncMock(), AsyncMock()
        with patch.object(worker, 'create_job_segment_runs_for_job_run', AsyncMock(return_value=[row])), patch.object(worker, 'process_job_segment_run', AsyncMock()):
            await worker._process_job_run(job, definitions, jobs, AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), session)
        jobs.set_error.assert_awaited_once()
        self.assertIn('2', jobs.set_error.await_args.kwargs['error'])
        jobs.set_status.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
