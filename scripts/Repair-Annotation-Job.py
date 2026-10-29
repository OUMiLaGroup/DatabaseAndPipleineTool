"""Run inside cvat_worker; retry incomplete segments without replacing completed outputs."""
import argparse
import asyncio
import sys
sys.path.insert(0, '/app')
import main as worker
from db.enums import CameraType


async def repair(args):
    worker.load_builtin_cvat_detection_plugins()
    engine = worker.create_async_engine(worker.build_database_url())
    async with worker.async_sessionmaker(engine, expire_on_commit=False)() as session:
        definitions = worker.build_job_definition_service(session=session)
        jobs = worker.build_job_run_service(session=session)
        segments = worker.build_segment_service(session=session)
        runs = worker.build_job_segment_run_service(session=session)
        camera = CameraType(args.camera)
        job = await jobs.get_job_run(job_run_num=args.run, job_def_id=args.job, route_id=args.route, camera=camera)
        if job is None:
            raise ValueError('Job run not found')
        definition = await definitions.get_job_definition(args.job)
        rows = await runs.get_segments_by_job_run(args.run, args.job, args.route, camera)
        pending = [s for s in rows if s.status != worker.JobSegmentRunStatus.SUCCEEDED or s.artifact_id is None]
        if not rows:
            raise ValueError('No annotation segments exist; queue a new job run instead')
        if job.status == worker.JobStatus.RUNNING:
            raise ValueError('Job is already running; wait for it to finish')
        frames = worker.FrameService(worker.FrameRepository(session=session))
        frame_artifacts = worker.FrameArtifactService(worker.FrameArtifactRepository(session=session))
        artifacts = worker.ArtifactService(worker.ArtifactRepository(session=session))
        minio = worker.MinioService()
        downloader = worker.FrameArtifactDownloaderService(frame_service=frames, frame_artifact_service=frame_artifacts, artifact_service=artifacts, minio_service=minio)
        segment_downloader = worker.SegmentArtifactDownloadService(frame_service=frames, frame_artifact_downloader_service=downloader)
        await jobs.set_error(args.run, args.job, args.route, camera, None)
        await jobs.set_status(args.run, args.job, args.route, camera, worker.JobStatus.RUNNING)
        await session.commit()
        for segment in pending:
            print(f'Retrying segment {segment.segment_id}; completed outputs preserved', flush=True)
            await worker.process_job_segment_run(job_definition=definition, job_segment_run=segment, job_segment_run_service=runs, segment_service=segments, segment_artifact_download_service=segment_downloader, cvat_service=worker.CVATService(), minio_service=minio, artifact_service=artifacts, session=session)
        incomplete = [s.segment_id for s in rows if s.status != worker.JobSegmentRunStatus.SUCCEEDED or s.artifact_id is None]
        if incomplete:
            await jobs.set_error(args.run, args.job, args.route, camera, f'Annotation still incomplete for segments {incomplete}. Check CVAT worker logs.')
        else:
            await jobs.set_status(args.run, args.job, args.route, camera, worker.JobStatus.SUCCEEDED)
        await session.commit()
        print('Repair completed' if not incomplete else f'Repair failed for segments {incomplete}', flush=True)
    await engine.dispose()
    if incomplete:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--route', required=True)
    parser.add_argument('--job', type=int, required=True)
    parser.add_argument('--run', type=int, required=True)
    parser.add_argument('--camera', choices=['front_regular', 'front_wide'], required=True)
    asyncio.run(repair(parser.parse_args()))
