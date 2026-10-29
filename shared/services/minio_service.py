import logging
import os
from pathlib import Path
import time

from minio.deleteobjects import DeleteObject
from minio.datatypes import Bucket
from minio.helpers import ObjectWriteResult
from urllib3.response import BaseHTTPResponse

from db.models.artifact import Artifact
from db.models.job_segment_run import JobSegmentRun
from db.models.segment import Segment
from utilities.minio_utilities import get_job_segment_run_object_name, get_minio_client, get_segment_image_object_name, get_segment_log_object_name, is_bucket_in_list_of_buckets

logger = logging.getLogger(__name__)

class MinioService:
    def __init__(self):
        self.minio_client = get_minio_client()
        self.bucket_name = os.environ["MINIO_BUCKET_NAME"]

    def put_segment_image(self, segment: Segment, camera_view: str, frame_number: int, frame_path: Path) -> ObjectWriteResult:
        """
        Returns the Minio Object Name 
        """
        result = self.minio_client.fput_object(
            bucket_name=self.bucket_name,
            object_name=get_segment_image_object_name(segment, camera_view, frame_number),
            content_type="image/png",
            file_path=str(frame_path)
        )
        return result

    def put_segment_log(self, segment: Segment, log_path: Path) -> ObjectWriteResult:
        return self.minio_client.fput_object(
            bucket_name=self.bucket_name,
            object_name=get_segment_log_object_name(segment),
            content_type="application/json",
            file_path=str(log_path)
        )

    def put_job_segment_run_data(self, job_segment_run: JobSegmentRun, file_path: Path) -> ObjectWriteResult:
        is_zip = file_path.suffix.lower() == ".zip"
        object_name = get_job_segment_run_object_name(job_segment_run)
        if is_zip:
            object_name = object_name.removesuffix("data.json") + f"{job_segment_run.camera.value}/depth-labels.zip"
        return self.minio_client.fput_object(
            bucket_name=self.bucket_name,
            object_name=object_name,
            content_type="application/zip" if is_zip else "application/json",
            file_path=str(file_path)
        )

    def put_dataset_export_zip(
        self,
        route_id: str,
        export_id: int,
        file_path: Path,
    ) -> ObjectWriteResult:
        return self.minio_client.fput_object(
            bucket_name=self.bucket_name,
            object_name=f"exports/{route_id}/{export_id}.zip",
            content_type="application/zip",
            file_path=str(file_path),
        )


    def wait_for_minio(self, timeout: int = 30) -> None:
        start = time.time()
        while True:
            try:
                self.minio_client.list_buckets()
                return
            except Exception:
                if time.time() - start >  timeout:
                    raise RuntimeError("Minio not ready")
                time.sleep(1)

    def list_buckets(self) -> list[Bucket]:
        return self.minio_client.list_buckets()

    def is_main_bucket_in_created(self):
        return is_bucket_in_list_of_buckets(
            target=self.bucket_name,
            buckets=self.list_buckets()
        )

    def create_bucket(self, bucket_name: str) -> None:
        self.minio_client.make_bucket(
            bucket_name=bucket_name,
        )

    def download_artifact(self, artifact:Artifact,  dest_path:Path):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self.minio_client.fget_object(
            bucket_name=artifact.bucket, 
            object_name=artifact.object_key, 
            file_path=str(dest_path)
        )

    def delete_object(self, bucket_name: str, object_key: str) -> None:
        logger.info(f"deleting artifcat {object_key}")
        self.minio_client.remove_object(bucket_name=bucket_name, object_name=object_key)

    def delete_objects(self, bucket_name: str, object_keys: list[str]) -> None:
        delete_objects = [DeleteObject(object_key) for object_key in object_keys]
        for object_key in object_keys:
            logger.debug(f"deleting artifcat {object_key}")

        errors = self.minio_client.remove_objects(
            bucket_name=bucket_name,
            delete_object_list=delete_objects,
        )

        for error in errors:
            logger.error(f"Error deleting object from minio: {error}")

    def get_object_stream(
        self,
        bucket_name: str,
        object_key: str,
    ) -> BaseHTTPResponse:
        return self.minio_client.get_object(
            bucket_name=bucket_name,
            object_name=object_key,
        )

    def stream_object(
        self,
        bucket_name: str,
        object_key: str,
        chunk_size: int = 1024 * 1024,
    ):
        object_stream = self.get_object_stream(
            bucket_name=bucket_name,
            object_key=object_key,
        )
        try:
            for chunk in object_stream.stream(amt=chunk_size):
                yield chunk
        finally:
            object_stream.close()
            object_stream.release_conn()
