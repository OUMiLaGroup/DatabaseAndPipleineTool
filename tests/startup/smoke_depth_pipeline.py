"""Exercise the production depth segment and export paths on one real frame.

Uses temporary storage objects and fake DB services; never changes route jobs.
Run in cvat_worker with dataset_export_worker/main.py copied to /depth_export_main.py.
"""
import asyncio
import importlib.util
import json
import sys
sys.path.insert(0, "/app")
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
import main as worker
from db.enums import ArtifactKind, CameraType, JobType, JobSegmentRunStatus
from services.minio_service import MinioService


async def verify():
    storage = MinioService()
    prefix = "v1/routes/db478799b6f9f210|0000000e--9ecd39f6bc/segment/0/front_regular/frames/"
    image = next(storage.minio_client.list_objects(storage.bucket_name, prefix=prefix))
    frame_id = int(Path(image.object_name).stem)
    row = SimpleNamespace(route_id=f"validation-depth-{uuid4()}", job_def_id=0, job_run_num=0,
                          segment_id=0, camera=CameraType.FRONT_REGULAR, artifact_id=None,
                          status=JobSegmentRunStatus.QUEUED)
    definition = SimpleNamespace(type=JobType.DEPTH, implementation_key="depth_anything_3",
                                 config={"process_res": 280, "device": "cpu"})
    artifacts = {}

    async def create_artifact(**fields):
        artifact = SimpleNamespace(artifact_id=uuid4(), **fields)
        artifacts[artifact.artifact_id] = artifact
        return artifact

    async def set_status(**fields):
        row.status = fields["status"]

    async def download_segment_frames(**fields):
        destination = fields["dest_path"]
        destination.mkdir(parents=True, exist_ok=True)
        storage.minio_client.fget_object(storage.bucket_name, image.object_name,
                                        str(destination / f"{frame_id:05}.png"))

    artifact_service = SimpleNamespace(create_artifact=AsyncMock(side_effect=create_artifact),
                                       get_artifact=AsyncMock(side_effect=lambda artifact_id: artifacts[artifact_id]))
    segment_service = SimpleNamespace(get_segment=AsyncMock(return_value=SimpleNamespace()))
    runs = SimpleNamespace(set_status=AsyncMock(side_effect=set_status),
                           get_segments_by_job_run=AsyncMock(return_value=[row]))
    downloader = SimpleNamespace(download_segment_frames=AsyncMock(side_effect=download_segment_frames))
    try:
        await worker.process_job_segment_run(definition, row, runs, downloader, segment_service,
                                              artifact_service, None, storage, AsyncMock())
        assert row.status == JobSegmentRunStatus.SUCCEEDED
        assert artifacts[row.artifact_id].kind == ArtifactKind.ZIP
        spec = importlib.util.spec_from_file_location("depth_export_worker", "/depth_export_main.py")
        exporter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(exporter)
        with TemporaryDirectory() as folder:
            export_root = Path(folder)
            await exporter._download_job_outputs([row], export_root, runs, artifact_service, storage)
            output_dir = export_root / "job_runs/front_regular/0/0/segments/0"
            index = json.loads((output_dir / "data.json").read_text())
            label = index["images"][0]
            with np.load(output_dir / label["depth_file"], allow_pickle=False) as values:
                assert values["depth"].shape == (label["height"], label["width"])
                assert values["valid"].dtype == bool
                assert label["units"] == "focal_normalized"
                print(json.dumps({"production_segment": "passed", "minio_roundtrip": "passed",
                                  "export_extraction": "passed", "shape": list(values["depth"].shape),
                                  "valid_pixels": int(values["valid"].sum())}))
    finally:
        for artifact in artifacts.values():
            storage.minio_client.remove_object(artifact.bucket, artifact.object_key)


asyncio.run(verify())
