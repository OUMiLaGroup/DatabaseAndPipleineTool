# Windows startup launcher

For the integrated workspace, double-click **Start-MiLa-GUI.cmd** or
**MiLa-Launcher.exe**. It requires Python 3.10+ with Tcl/Tk and automatically
installs missing browser support. It collects credentials, installs prerequisites,
shows progress, and embeds MiLa and CVAT in native tabs. See
[GUI setup details](../launcher/README.md). Use `-Tkinter` for the original GUI.
The console workflow below remains available for troubleshooting and rebuilds.

Double-click **Start-MiLa.cmd** in the project root. It runs with Windows
PowerShell 5.1; no extra Python or PowerShell modules are needed on the host.
The dashboard opens only after startup checks pass. Errors stay visible in the
launcher window. Docker services continue running when you close that window.

## First use

1. Install and start Docker Desktop with the WSL 2 backend and Linux containers.
   Install Git for Windows if the project does not yet contain a `cvat` checkout.
2. Run the launcher once. If `.env` is absent, it copies `.example_env` and stops.
   Edit `.env` and fill in the database, MinIO, Comma JWT, and CVAT credentials.
   Use Compose dotenv quoting for special characters (single quotes preserve
   literal dollar signs). Never commit this file.
3. Put your MinIO AIStor license at `minio/minio.license` (see the main README).
4. Run **Start-MiLa.cmd** again. Allow time and internet access for downloads
   and the initial OpenPilot build. Build time is separate from readiness waits.

The launcher checks Docker, configuration, and the license; downloads CVAT if
absent; creates the shared network; starts PostgreSQL and MinIO; applies the
checked-in Alembic migrations; creates the bucket if needed; starts CVAT; creates
its first account or verifies the existing password; and starts the application
and workers. It does not generate migrations or overwrite existing passwords.
Database schema upgrades modify the database: maintain backups when upgrading
the project. Running it again preserves existing containers by default.

The Windows CVAT override uses direct bind mounts, rather than the Linux local
volume-driver path in the original setup script. Existing CVAT checkouts are
reused and never pulled automatically. First setup follows the original script's
upstream default branch; for a reproducible deployment, place a team-approved,
pinned CVAT checkout in `cvat` first. Do not run both setup methods simultaneously.

## Options

Run from the project root in PowerShell:

```powershell
# Read-only prerequisite checks (does not create .env or clone CVAT)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-MiLa.ps1 -CheckOnly

# Start without opening a browser
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-MiLa.ps1 -NoBrowser

# Rebuild application images after source/configuration changes
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-MiLa.ps1 -Rebuild

# Allow slower service startup (seconds per readiness check)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-MiLa.ps1 -TimeoutSeconds 600
```

Use `-Rebuild` only when processing jobs are idle: replacing workers interrupts
their jobs. Normal startup does not automatically apply changed environment
settings to existing containers. Initial setup still requires credentials and
third-party prerequisites; this launcher is not an unattended OS installer.

## Troubleshooting

- **MetaDrive wheel hash mismatch during OpenPilot build:** the download worker
  now excludes OpenPilot v0.9.8's optional `tools` extra (MetaDrive and rerun-sdk).
  Recorded-drive replay/extraction does not use these simulator/visualization
  packages. The upstream lockfile and installed-package checksum checks remain
  enabled. Rerun the launcher after updating the source; the failed image will
  build again. This worker image is not intended to run MetaDrive simulation.

- **Windows "failed to get console: The handle is invalid":** the launcher
  uses plain Compose/BuildKit progress, disables ANSI output and setup-job TTYs,
  and leaves native stdout unpiped. Use the updated launcher from this project;
  no database reset is needed. If it persists, record `docker compose version`
  and the error from a direct PowerShell command:
  `docker compose --ansi never --progress plain run --rm --no-deps -T --interactive=false alembic_worker`.

- **Git "Filename too long":** new launcher clones enable `core.longpaths`
  for the CVAT repository only. An interrupted initial checkout with no Git
  index is completed automatically on the next launch, preserving existing
  files. No global Git settings are changed. If another tool still rejects
  long paths, use a shorter project location such as `C:\MiLa`.

- **Docker missing/unavailable:** install/start Docker Desktop, select Linux
  containers, and reopen the launcher after installation.
- **Port conflict:** this project uses 5173, 8000, 8080, 9000, 9001, and 5433.
  Resolve the conflicting application before retrying.
- **Timeout:** inspect the relevant service in Docker Desktop. From the project
  root, use `docker compose ps` and `docker compose logs --tail 100 SERVICE`.
  For CVAT, use `docker logs --tail 100 cvat_server`.
- **CVAT login mismatch:** correct `.env` to match the existing account. The
  launcher deliberately does not reset the account's password.
- **Partial startup:** already-started services are left running for diagnosis;
  fix the error and rerun. No data directories or Docker volumes are deleted.
- **Stopping:** use Docker Desktop to stop this project's application and CVAT
  containers when processing is idle. Closing the launcher does not stop them.

Checks establish HTTP availability and that application containers are running.
They do not prove worker initialization, model downloads, credentials for Comma,
or a complete import/annotation/export workflow. Validate with a small route.
The launcher does not restart frozen CVAT services automatically.

## Launcher tests

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\startup\Test-Startup.ps1
```

These isolated tests simulate Docker and HTTP responses. They verify ordering,
failure handling, prerequisites, and safe repeated startup without downloading
images or starting containers. A real Docker smoke test is still required.
