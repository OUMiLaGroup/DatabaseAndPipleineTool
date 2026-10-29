# Error Guide: Finding and Fixing Problems

This guide explains the errors the pipeline can show and how to fix them. Every error has a short
**code** (for example `ROUTE_NOT_READY`); search this page for the code you see.

- [Reading an error](#reading-an-error)
- [Troubleshooting step by step](#troubleshooting-step-by-step)
- [Activity page (audit log)](#activity-page-audit-log)
- [Error codes](#error-codes)
- [Failure reasons shown on routes, segments and job runs](#failure-reasons-shown-on-routes-segments-and-job-runs)
- [Setup and environment problems](#setup-and-environment-problems)
- [For developers: adding a new error](#for-developers-adding-a-new-error)

---

## Reading an error

Errors appear in three places:

| Where | Example |
|---|---|
| **Toast** (bottom-right) | An action failed, e.g. importing a route that already exists |
| **Inline box** in a form | The form's own action failed, e.g. *Could not create job run* |
| **Failure reason** on a route, segment, job run or CVAT import | Background work failed, e.g. a download or a job run. Click the ▸ line to expand it |

Each error shows:

- **Message**: what went wrong.
- **How to fix**: the most likely fix. Try this first.
- **code**: the error code to look up below.
- **request**: a request ID (API errors only). Click it to copy it, then find the full details in the backend logs:
  ```bash
  docker compose logs backend | grep <request-id>
  ```

Failures stored on routes, segments and job runs use the format
`<what went wrong> | How to fix: <hint>`.

A route or job run in **amber** (warning) partly succeeded: for example
`2 of 10 segments failed (segments: 3, 7). First error (segment 3): ...`. The successful segments are
still usable; the failed ones are listed with their reasons on the segment page.

---

## Troubleshooting step by step

1. **Read the "How to fix" line** and try it.
2. **Look up the code** in [Error codes](#error-codes).
3. **Check the Activity page** (top bar → *Activity*, filter *Failed*) to see what else failed around
   the same time. Open a route and click **View activity →** to see only that route.
4. **Check that everything is running:**
   ```bash
   docker compose ps
   ```
   `backend`, `frontend`, `postgres`, `minio` and the workers should be `Up`.
   `alembic_worker` and `minio_initializer` exit after they finish; that is normal.
5. **Read the logs** of the service involved:
   ```bash
   docker compose logs --tail 100 backend
   docker compose logs --tail 100 cvat_worker
   docker compose logs --tail 100 open_pilot_download_worker
   docker compose logs --tail 100 open_pilot_upload_worker
   docker compose logs --tail 100 cvat_import_export_worker
   docker compose logs --tail 100 dataset_export_worker
   ```
   Errors are logged as `ERROR [<service>] ...` followed by the full traceback.
   For more detail, set `LOG_LEVEL=DEBUG` for that service and restart it.
6. **Still stuck?** Share the error code, the request ID and the log lines with the team.

---

## Activity page (audit log)

The **Activity** page (top bar) is a permanent record of what happened, newest first:

- **Every change made in the app**: importing/deleting routes, creating/cancelling/retrying/deleting
  job runs, job definitions, CVAT load/remove, CVAT restarts and dataset exports. Failed attempts are
  recorded too, with the error code and request ID the user saw.
- **The outcome of all background work**: route downloads and uploads, job runs, CVAT imports and
  dataset exports (`... finished` with *Success*, *Warning* or *Failed*), and work that was
  **interrupted** because a worker restarted.

Filter by outcome, type, source (the app or a specific worker) or route ID. Filters are kept in the
URL, so you can share a link such as `/activity?route=<route-id>&outcome=failure`.

The same data is available from the API: `GET /audit-logs/?route_id=...&outcome=failure&limit=100`
(see http://localhost:8000/docs). Older entries are paged with `before_id=<last id>`.

The app has no user accounts, so entries record *what* did something (the app or a named worker),
not *which person*. Entries are kept when a route is deleted.

---

## Error codes

### Routes

#### ROUTE_ALREADY_EXISTS
The route was already imported.
**Fix:** open it from the dashboard. To import it again, delete it first.

#### ROUTE_NOT_FOUND
No route with that ID exists in the pipeline.
**Fix:** check the ID (format `<dongle_id>|<log_id>`, e.g. `db478799b6f9f210|0000000e--9ecd39f6bc`).
It may have been deleted; refresh the dashboard.

#### INVALID_ROUTE_ID
The route ID is not in the expected format.
**Fix:** use `<dongle_id>|<log_id>`. Links copied from connect.comma.ai use `/` instead of `|`;
replace it. Make sure the separator before the log hash is two hyphens `--`; macOS sometimes turns
`--` into a long dash `—` while typing.

#### ROUTE_NOT_READY
Job runs can only be created when the route status is **UPLOADED**.
**Fix:** wait for the download and upload to finish (the route card shows progress). If the route is
**FAILED**, read its failure reason, fix the cause, then delete and re-import it.

#### ROUTE_HAS_NO_SEGMENTS
The route has no segments to process.
**Fix:** the download may not have finished or every segment failed to download. Open the route to
see why, then delete and re-import it.

#### ROUTE_DELETE_BLOCKED
The route can't be deleted while it is busy.
**Fix:** wait for its job runs and CVAT imports to finish, then delete it.

### comma.ai (route download)

#### COMMA_AUTH_FAILED
comma.ai rejected the request (HTTP 401/403/404). The `COMMA_JWT` token is missing, expired, or
can't see this device.
**Fix:** get a new token from https://jwt.comma.ai, put it in `.env` as `COMMA_JWT=...`, then rebuild
the download worker (the token is used at build time):
```bash
docker compose up --build -d open_pilot_download_worker
```
Then delete and re-import the route.

#### COMMA_ROUTE_NOT_FOUND
The device exists but has no route with this ID.
**Fix:** check the ID for typos and check on https://connect.comma.ai that the route still exists and
has finished uploading from the car.

#### COMMA_API_ERROR
comma.ai could not be reached or returned a server error.
**Fix:** check your internet connection and try again later.

### Segments and frames

#### SEGMENT_NOT_FOUND
The segment doesn't exist for this route.
**Fix:** segments that failed to download are skipped. Check the segment list on the route page.

#### FRAME_NOT_FOUND
No frames were found for the segment.
**Fix:** the segment may still be uploading, or its upload failed. Check the segment status and its
failure reason on the route page.

#### ARTIFACT_NOT_FOUND, SEGMENT_ARTIFACT_NOT_FOUND, FRAME_ARTIFACT_NOT_FOUND, JOB_FRAME_ARTIFACT_NOT_FOUND
A stored file (image, log, detection result or export zip) is missing.
**Fix:** check that MinIO is running (http://localhost:9001, `docker compose ps minio`) and that the
bucket still exists. Deleting and re-importing the route regenerates its files. If MinIO's data folder
was wiped, the database still references files that no longer exist; re-import the affected routes.

### Job definitions

#### JOB_DEFINITION_NOT_FOUND
The job definition doesn't exist (it may have been deleted).
**Fix:** refresh the *Jobs* page and pick another definition, or create a new one.

#### JOB_DEFINITION_ALREADY_EXISTS
A job definition with this ID already exists. This is an internal error.
**Fix:** refresh and try again; report it if it repeats.

### Job runs

#### JOB_RUN_NOT_FOUND
The job run doesn't exist (it may have been deleted).
**Fix:** refresh the route page.

#### JOB_RUN_CANCEL_NOT_ALLOWED
Only **QUEUED** job runs can be cancelled.
**Fix:** a RUNNING job has to finish. Finished job runs (SUCCEEDED, FAILED, CANCELLED) can be deleted
instead.

#### JOB_RUN_REQUEUE_NOT_ALLOWED
Only **CANCELLED** job runs can be retried with *Retry*.
**Fix:** to retry a FAILED job run, queue a new job run with the same job definition.

#### JOB_RUN_ACTIVE
The route still has QUEUED or RUNNING job runs.
**Fix:** cancel the queued ones, wait for running ones to finish, then try again.

#### JOB_SEGMENT_RUN_NOT_FOUND
The job run has no result for this segment.
**Fix:** the job may still be running, or the segment failed during the job. Check the job run's
status and the segment's failure reason.

### CVAT

#### CVAT_UNAVAILABLE
The pipeline can't connect to or log in to CVAT.
**Fix:**
1. Check CVAT is running: `docker ps --filter name=cvat_server`. If not, run `./scripts/setup_cvat.sh`.
2. Check `CVAT_EMAIL` and `CVAT_PASSWORD` in `.env` match a CVAT user (log in at http://localhost:8080).
3. After a restart, CVAT can take a minute to come up; wait and retry.

#### CVAT_RESTART_FAILED
*Refresh CVAT* could not restart the `cvat_server` container.
**Fix:** check Docker is running, that the container exists (`docker ps -a --filter name=cvat_server`;
if not, run `./scripts/setup_cvat.sh`), and that `/var/run/docker.sock` is mounted into the backend
(it is in `docker-compose.yaml`).

#### CVAT_BUSY
CVAT can't be restarted while job runs or CVAT imports are active.
**Fix:** wait for them to finish, then click *Refresh CVAT* again.

#### CVAT_IMPORT_NOT_FOUND
This segment hasn't been sent to CVAT for this job run.
**Fix:** use the CVAT button on the segment page to load it.

#### CVAT_IMPORT_BUSY
A CVAT import is still loading or being removed.
**Fix:** wait until it shows LOADED, REMOVED or FAILED, then try again.

### Dataset exports

#### DATASET_EXPORT_INVALID
The export request isn't valid.
**Fix:** an export needs a route with status **UPLOADED**, at least one camera view that exists on the
route (no duplicates), and only job runs with status **SUCCEEDED**.

#### DATASET_EXPORT_NOT_FOUND
The export doesn't exist (it may have been deleted).
**Fix:** refresh the page.

#### DATASET_EXPORT_RUNNING
A running export can't be deleted.
**Fix:** wait until it is SUCCEEDED or FAILED, then delete it.

### Audit log

#### INVALID_AUDIT_FILTER
An unknown filter value was sent to `GET /audit-logs/`.
**Fix:** `outcome` must be `success`, `warning` or `failure`.

### General errors

#### VALIDATION_ERROR
The request was missing a field or had a value of the wrong type (HTTP 422). The message lists the
fields, e.g. `Invalid request: name: Field required`.
**Fix:** correct the listed fields and try again.

#### INTERNAL_ERROR
An unexpected error on the server (HTTP 500): a bug, or a service such as Postgres, MinIO or CVAT is
down.
**Fix:** find the traceback with `docker compose logs backend | grep <request-id>`, and check
`docker compose ps`.

#### NETWORK_ERROR
The app could not reach the backend at all.
**Fix:** start it with `docker compose up -d backend` and check http://localhost:8000/health-check
returns `{"status":"alive"}`. If you changed ports, check `VITE_API_URL` for the frontend.

#### SERVER_ERROR, REQUEST_FAILED, NOT_FOUND, CONFLICT, ALREADY_EXISTS, PIPELINE_ERROR
Generic codes used when a more specific one isn't available.
**Fix:** read the message, then follow [Troubleshooting step by step](#troubleshooting-step-by-step).

#### ARTIFACT_ALREADY_EXISTS, SEGMENT_ALREADY_EXISTS, SEGMENT_ARTIFACT_ALREADY_EXISTS, FRAME_ALREADY_EXISTS, FRAME_ARTIFACT_ALREADY_EXISTS, JOB_FRAME_ARTIFACT_ALREADY_EXISTS, JOB_RUN_ALREADY_EXISTS, JOB_SEGMENT_RUN_ALREADY_EXISTS
Internal "duplicate record" errors raised by the workers, usually after a crash part-way through.
**Fix:** delete and re-import the route (or delete and re-queue the job run). Report it if it repeats.

---

## Failure reasons shown on routes, segments and job runs

These come from the background workers and are shown on the item and on the Activity page.

| Reason starts with | Meaning | Fix |
|---|---|---|
| `The <worker> restarted while ...` | The worker stopped (crash, rebuild, `docker compose restart`) during the work, so it was marked failed on startup. | Retry: delete and re-import the route, queue a new job run, or *Retry* the export. If the worker keeps restarting, check its logs for crashes or out-of-memory errors. |
| `N of M segments failed ...` | Some segments failed; the first error is included. Amber means the rest succeeded. | Open the failed segments to see each reason. |
| `N of M segments failed to download` | Some segments could not be extracted from comma.ai. | See the segment's reason; usually a replay/extraction error, below. |
| `RuntimeError: extraction exited with code ...` / `replay exited early ...` | openpilot could not replay or extract the segment. | Check `docker compose logs open_pilot_download_worker`. The segment may be incomplete on comma.ai; re-import later. |
| `route processing exceeded timeout` | Extraction took longer than `ROUTE_PROCESS_TIMEOUT_SECONDS`. | Increase the timeout or retry. |
| `Route ... has no file_path` | The upload worker can't find the downloaded files. | Delete and re-import the route. |
| `Failed while loading into CVAT: ...` / `Failed while removing from CVAT: ...` | The CVAT import worker failed; the reason follows. | Usually `CVAT_UNAVAILABLE`: see above. |
| Ends with *How to fix: Check that the postgres container is running* | A database error. | `docker compose ps postgres`; restart it if needed. |
| Ends with *How to fix: The disk is full* | No space left. | Free space (`docker system prune`, clear `./data` and `./data_exports`). |

---

## Setup and environment problems

#### `failed to connect to the docker API ... docker.sock: no such file or directory`
Docker isn't running. Open Docker Desktop (`open -a Docker`) and wait until it says it is running.
If it is running and the error remains, run `docker context use desktop-linux`.

#### `no such service: #`
A `# comment` was pasted after a command. Run the command without the comment.

#### `network cvat_network declared as external, but could not be found`
CVAT hasn't been set up. Run `./scripts/setup_cvat.sh` once; it creates the network.

#### `The container name ... is already in use`
Two `docker compose up` commands ran at the same time. It is harmless; check `docker compose ps`.

#### Download worker build fails on Apple Silicon (`rosetta error: failed to open elf at /lib64/ld-linux-x86-64.so.2`)
The openpilot setup installs the Intel (x86_64) Miniconda. On an M-series Mac, build that image as Intel:
1. Docker Desktop → Settings → General → enable **Use Rosetta for x86_64/amd64 emulation on Apple Silicon**.
2. `DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose up --build -d open_pilot_download_worker`

This is slow (30+ minutes the first time).

#### `cvat_worker` takes a very long time to build
PyTorch and its CUDA libraries are several GB. Let it finish; later builds are cached.

#### A worker's logs are empty
Workers only log when they start, become ready and process work. `cvat_worker` logs
`Ready: polling ...` once started; if nothing appears after ~30 seconds, check `docker compose ps`.

#### `column "error" does not exist` / `relation "audit_logs" does not exist`
The database migrations haven't been applied. Run:
```bash
docker compose up --build alembic_worker
docker compose restart backend
```
Don't run `alembic revision --autogenerate` for this; the migration files are already in the repo.

#### Containers fail with `KeyError: 'POSTGRES_USER'` (or another variable)
`.env` is missing or incomplete. It must be in the project folder and contain `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET_NAME`,
`CVAT_EMAIL`, `CVAT_PASSWORD` and `COMMA_JWT`. Never commit it.

#### MinIO won't start
Check `minio/minio.license` exists (see the README) and that ports 9000/9001 are free.

#### `port is already allocated`
Another program uses the port (5173, 8000, 8080, 9000, 9001 or 5433). Stop it, or stop the old
containers with `docker compose down`.

---

## For developers: adding a new error

1. Add a class to `shared/services/errors.py` that subclasses `PipelineError` (or `NotFoundError`,
   `ConflictError`, `AlreadyExistsError`) and set `code`, `status_code` and `hint`.
2. Raise it. The backend returns it in the standard format and the frontend displays it; no new
   handler is needed.
3. **Add the code to this guide.** `tests/unit/test_error_guide.py` fails if a code is missing here.
4. In workers, store failures with `describe_exception()` / `record_failure()` and record the outcome
   with `record_audit()` (see `shared/utilities/error_utilities.py` and
   `shared/services/audit_service.py`).
