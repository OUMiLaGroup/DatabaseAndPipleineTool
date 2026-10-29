import os
from pathlib import Path
import time
import logging
import zipfile

from cvat_sdk.core.client import Client
import docker
from cvat_sdk.core.proxies.tasks import ResourceType, Task
from cvat_sdk.models import TaskWriteRequest
import cvat_sdk.auto_annotation as cvataa

from cvat_annotation_functions.i_cvat_detection import ICVATDetection
from db.enums import JobSegmentRunImportStatus, JobStatus
from models.job_segment_run_dir import JobSegmentRunDir
from services.errors import CVATActiveError, CVATRestartError, CVATUnavailableError
from services.job_run_service import JobRunService
from services.job_segment_run_import_service import JobSegmentRunImportService
from utilities.cvat_utilities import create_cvat_client, labels_to_patched_requests, extract_ids_to_labels_for_coco_annotation_file
from utilities.file_utilities import does_dir_exist, get_pngs_in_directory

logger = logging.getLogger(__name__)

CVAT_CONTAINER_NAME = "cvat_server"
RESTART_TIMEOUT_SECONDS = 10
ACTIVE_IMPORT_STATUSES: list[JobSegmentRunImportStatus] = [
    JobSegmentRunImportStatus.LOADING,
    JobSegmentRunImportStatus.REMOVING,
]


class CVATService:
    def __init__(self):
        self._cvat_client: Client | None = None

    @property
    def cvat_client(self) -> Client:
        if self._cvat_client is None:
            self._cvat_client = create_cvat_client()
        return self._cvat_client

    async def is_active(
        self,
        job_run_service: JobRunService,
        import_service: JobSegmentRunImportService,
    ) -> bool:
        if await job_run_service.get_next_job_run_by_status(JobStatus.RUNNING) is not None:
            return True
        if await import_service.get_next_by_statuses(ACTIVE_IMPORT_STATUSES) is not None:
            return True
        return False

    async def restart_server(
        self,
        job_run_service: JobRunService,
        import_service: JobSegmentRunImportService,
    ) -> float:
        if await self.is_active(job_run_service, import_service):
            raise CVATActiveError()

        logger.info("Restarting %s container", CVAT_CONTAINER_NAME)
        started = time.monotonic()
        self._restart_container()
        return time.monotonic() - started

    def _restart_container(self) -> None:
        try:
            client = docker.from_env()
            container = client.containers.get(CVAT_CONTAINER_NAME)
            container.restart(timeout=RESTART_TIMEOUT_SECONDS)
        except Exception as e:
            logger.exception("Failed to restart %s container", CVAT_CONTAINER_NAME)
            raise CVATRestartError(f"Could not restart the {CVAT_CONTAINER_NAME} container: {e}") from e

    def check_cvat_connection(self):
        try:
            self.cvat_client.tasks.list(return_json=False)
        except Exception as e:
            raise CVATUnavailableError(f"Failed to connect/authenticate to CVAT: {e}") from e

    def wait_for_cvat(self, max_wait_seconds: int = 60, poll_interval: int = 3) -> None:
        deadline = time.time() + max_wait_seconds
        last_error = None
        while time.time() < deadline:
            try:
                self.check_cvat_connection()
                return
            except Exception as e:
                last_error = e
                time.sleep(poll_interval)

        raise CVATUnavailableError(f"CVAT did not become ready within {max_wait_seconds}s: {last_error}")

    def create_new_task_for_img_dir(self, segment_dir: Path, cvat_function: ICVATDetection) -> int:
        """
        Returns the task id of the created task
        """
        images = get_pngs_in_directory(dir=segment_dir)
        # logging.info(f"Creating new task with dir {segment_dir}")
        # logging.info(f"Create new task with images: {images}")
        labels = cvat_function.labels
        patched_labels = labels_to_patched_requests(labels=labels)
        task_spec = TaskWriteRequest(
            name=str(segment_dir),
            labels=patched_labels
        )
        logger.info(f"Creating cvat task with name {str(segment_dir)}")

        task = self.cvat_client.tasks.create_from_data(
            spec=task_spec, # type: ignore
            resource_type=ResourceType.LOCAL,
            resources=images,
            # Avoid large image chunks in Redis; prepare small chunks on disk.
            data_params={'use_cache': False, 'chunk_size': 16},
        )

        logger.info(f"Tak created with id {task.id}")
        return task.id

    def create_new_annotated_task_for_job_segment_run_dir(
        self,
        job_segment_run_dir: JobSegmentRunDir,
        task_name: str
    ) -> Task:
        """
        Returns the task id of the created task
        """

        logging.info(f"Creating cvat task from directory with name {task_name}")
        labels = extract_ids_to_labels_for_coco_annotation_file(
            annotation_file=job_segment_run_dir.annotation_path
        )
        patched_labels = labels_to_patched_requests(labels=labels)
        task_spec = TaskWriteRequest(
            name=task_name,
            labels=patched_labels
        )
        logging.info(job_segment_run_dir)
        task = self.cvat_client.tasks.create_from_data(
            spec=task_spec, # type: ignore
            resources=job_segment_run_dir.image_paths,
            resource_type=ResourceType.LOCAL,
            annotation_path=str(job_segment_run_dir.annotation_path),
            annotation_format="COCO 1.0"
        )
        logger.info(f"Created task with id {task.id}")
        return task

    def annotate_task(self, task_id: int, cvat_function: ICVATDetection) -> None:
        logging.info(f"Annotating CVAT Task: {task_id}")
        cvataa.annotate_task(
            self.cvat_client,
            task_id,
            cvat_function
        )

    def export_task_coco(
        self,
        task_id: int,
        output_dir: Path
    ) -> Path:
        """
        Args
            - task_id[int]: The task ID
            - output_dir[Path]: The path where data will be downloaded to
        Output
            - output_path[Path]: The file path of the output json file.
        """
        zip_path = output_dir / f"task_{task_id}.zip"
        out_path = output_dir / f"task_{task_id}.json"

        task = self.cvat_client.tasks.retrieve(obj_id=task_id)
        task.export_dataset(
            format_name="COCO 1.0",
            filename=zip_path,
            include_images=False
        )

        with zipfile.ZipFile(zip_path, "r") as zip_file:
            coco_files = [file for file in zip_file.namelist() if file.endswith(".json")]
            if not coco_files:
                raise FileNotFoundError(f"No coco files found in {zip_path} when exporting task {task_id}")

            with zip_file.open(coco_files[0]) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
        os.remove(zip_path)
        return out_path

    def get_detections_for_segment(self, segment_dir: Path, cvat_function: ICVATDetection, output_dir: Path) -> Path:
        """
        Returns the path of the output file
        """
        if not does_dir_exist(dir=segment_dir):
            raise RuntimeError(f"Directory {segment_dir} does not exist.")

        self.wait_for_cvat()
        task_id = self.create_new_task_for_img_dir(
            segment_dir=segment_dir,
            cvat_function=cvat_function
        )
        self.annotate_task(
            task_id=task_id,
            cvat_function=cvat_function
        )

        output_file = self.export_task_coco(
            task_id=task_id,
            output_dir=output_dir
        )


        self.delete_task(task_id=task_id)

        return output_file

    def delete_task(self, task_id: int):
        logging.info(f"Removing CVAT Task: {task_id}")
        self.cvat_client.tasks.remove_by_ids([task_id])
