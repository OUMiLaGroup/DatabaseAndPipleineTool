import os

from services.minio_service import MinioService
from utilities.logging_utilities import configure_logging

logger = configure_logging("minio_initializer")


def main():
    logger.info("Starting Minio Checks")
    minio_service = MinioService()

    try:
        logger.info("Waiting for Minio to be active...")
        minio_service.wait_for_minio()
        logger.info("Minio service active")
    except RuntimeError:
        logger.exception(
            "Could not reach Minio at %s. Check that the minio container is running "
            "(docker compose up -d minio) and that minio/minio.license exists.",
            os.environ.get("MINIO_ENDPOINT", "<MINIO_ENDPOINT not set>"),
        )
        raise

    if minio_service.is_main_bucket_in_created():
        logger.info("Minio bucket exists")
        return

    logger.info("Minio bucket does not exist, attempting creation...")
    minio_service.create_bucket(bucket_name=minio_service.bucket_name)
    logger.info("Created bucket")


if __name__ == "__main__":
    main()
