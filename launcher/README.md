# MiLa Windows launcher

For a new user, distribute **MiLa-Installer.exe** by itself. It includes the
application source and installs it under `%LOCALAPPDATA%\MiLa\Project`.
Missing Python (with Tcl/Tk and pip) and WebView2 download automatically before
the account screen opens. Python's official installer is checked against its
published SHA-256 checksum and Authenticode publisher. Internet access is required.
The preparation window shows activity while these dependencies install.
After entering credentials, **Install necessary components** downloads missing
Docker Desktop, Git, CVAT and container images through the existing setup flow.
Docker/Git installation wizards, Windows approval prompts, Docker terms and any
required reboot still need user interaction. A supported Windows AMD64 machine
with virtualization enabled is required; this is not an unattended installer.

Reopening the same installer reuses the installed folder and saved accounts.
Updates preserve account/license/data files and refuse to overwrite locally
edited source. The package excludes credentials, licenses, datasets, the CVAT
checkout and dependency caches. Build with
`powershell -ExecutionPolicy Bypass -File launcher\Build-Installer.ps1` after
editing sources. The executable is currently unsigned; sign release builds
before wider distribution. Validate the full installation on a clean Windows
machine before releasing it to customers.

Double-click `Start-MiLa-GUI.cmd` or the existing `MiLa-Launcher.exe` in the
project root. Both open the integrated workspace in `launcher/workspace.py`.
Account/Setup is editable in `launcher/workspace.html`; native tabs contain the
MiLa dashboard and CVAT. Python/HTML edits take effect on the next launch without
compiling the EXE. Keep the
launcher alongside the complete project folder.

The GUI uses **64-bit Python 3.10+ with Tcl/Tk**. The bootstrap finds compatible
Python on PATH, through `py`, in common installation directories, or in MiLa's
private runtime folder, and checks Tkinter before opening the app. If none is
available, it downloads and installs Python automatically for the current user.
The bootstrap installs `launcher/requirements.txt` (pywebview) if needed and
checks for Microsoft WebView2 Runtime. If missing, it downloads Microsoft's
official Evergreen bootstrapper, verifies its Authenticode signature and installs
the runtime. This initial browser setup happens before the main window opens;
internet access is required. Installation/startup still runs through Windows
PowerShell 5.1 and the existing Compose scripts.

For development, run directly from the project root:

```powershell
python -m pip install -r launcher\requirements.txt
python launcher\workspace.py
```

The **Existing Account / New Account** switch defaults to Existing Account when
saved credentials are detected, otherwise New Account. Existing Account hides
all credential inputs and Comma/MinIO help links; it loads the saved settings
when starting services. New Account reveals the form. The Account link provides
the saved details with secrets hidden by default. New Account creates settings
for a fresh project folder; selecting it does not replace accounts in an already
configured installation.

## Embedded dashboards

Download failures show a saved reason and suggested action on the route card and
detail page. Messages distinguish unavailable recordings, authentication/access,
connection issues and processing failures. Details are stored in the existing
route metadata, so no schema migration is required. After fixing the cause,
delete the failed route and import it again. Older failures without recorded
details display a fallback message instead of guessing the cause.

Successful installation ensures a **General Detection** job definition exists.
It uses the existing `detr_detection` plugin with its default
`PekingU/rtdetr_v2_r50vd` model. Open an uploaded route, choose **New Job Run**,
select **General Detection** and the camera, then click **Queue Job**. First execution
may download the model weights. Definition creation validates the configuration;
it does not confirm a complete annotation run. To recreate the definition after
deletion, run `launcher\Ensure-JobDefinitions.ps1` with PowerShell while the
backend is running. Existing definitions of that name are preserved.

**Account / Setup**, **MiLa Dashboard** and **CVAT** are native tabs in one window.
The dashboards load automatically when their services become reachable. After
startup succeeds, the app selects MiLa. Switching tabs preserves their documents,
including an open CVAT job. Back/Forward/Reload controls operate on the web page;
Reload does not restart containers. MiLa's links opening a local CVAT job in a
new window are routed into the existing CVAT tab.

CVAT still requires its normal login. Browser cookies/session data persist in a
separate profile for this project under `%LOCALAPPDATA%\MiLa\BrowserProfiles`.
The launcher does not automatically fill passwords in dashboard forms. Native
file pickers handle uploads; downloads show a Save dialog.

Each dashboard uses its own native WebView2 control, so CVAT's iframe-blocking
headers remain in effect. The Python account/install bridge is exposed only to
the local Account/Setup document; dashboard pages receive no Python account API.
External help links open in the normal browser.

The original Tkinter interface remains available for development/fallback:
`python launcher\mila_launcher.py` or `Start-MiLa-GUI.cmd -Tkinter`. It opens
dashboard links in the normal browser. It does not contain the embedded tabs.

## First installation

1. Double-click `MiLa-Installer.exe`. Alternatively, extract the full project
   into a short path such as `C:\MiLa` and use `MiLa-Launcher.exe`.
2. Enter a shared username (3-32 lowercase letters/digits/underscores, beginning
   with a letter) and a password of at least 12 characters.
3. Sign in to https://jwt.comma.ai with the Comma account authorized to access
   your driving data, then paste its JWT. A `google_...` ID is not a JWT. This
   application checks token structure; actual data access is verified when a
   route is processed. Comma's API documentation is https://api.comma.ai/.
4. Choose your separate MinIO AIStor license file. Obtain it from your project
   administrator or https://www.min.io/download. The launcher cannot issue a
   license or a Comma token for you.
5. Click **Install necessary components**. If Windows requests a restart,
   restart and reopen the same executable; the saved settings are reused.

New installs share the username/password across PostgreSQL, MinIO and CVAT.
CVAT uses `username@mila.local` as its local email/login identifier and the same
username before `@`. This is not a deliverable mailbox. MinIO uses the shared
username as its root/access-key ID. **Account** shows saved configuration values;
passwords and the JWT are hidden until explicitly revealed. `.env` remains a
local plaintext configuration required by Compose; Account is not an encrypted
password vault. Do not distribute `.env`, license files or existing data with a
release of the project.

An existing `.env` is preserved. Accounts created by previous versions are
displayed individually and are not silently renamed or reset. If `.env` is lost
but database/storage data remains, restore the original configuration. Converting
existing service accounts to a shared account requires a separate migration.
Account is read-only; fix an existing configuration in `.env` and reopen the app.

## What installation does

- Checks AMD64 architecture. ARM64 is blocked because the project's OpenPilot
  image currently downloads x86_64 tooling.
- Installs missing WSL without an extra Linux distribution, or updates versions
  below 2.1.5 when Docker is unavailable. Windows may request administrator approval
  and a restart. Firmware virtualization and organizational policies cannot be
  changed by this launcher.
- Downloads Docker Desktop AMD64 directly from Docker and Git for Windows from
  its official GitHub release when absent. Both installers must have valid
  Authenticode signatures matching their expected publishers before launch.
- Opens the official installation wizards. Users still accept Docker terms and
  respond to installer prompts. It does not accept those agreements silently.
- Starts Docker and waits up to 10 minutes for its Linux engine, then runs the
  existing five-stage `scripts/Start-MiLa.ps1` workflow.
- Pins Traefik to CVAT's own network. On older installations missing that label,
  startup recreates only the CVAT server once to apply the corrected routing.
  Its data volumes and accounts are retained; active CVAT sessions may be interrupted
  during this migration. Subsequent normal starts keep containers running.
- Downloads/builds CVAT, PostgreSQL, MinIO, the API, dashboard, processing workers,
  OpenPilot and their dependencies as needed. Existing data and containers are
  retained by the normal startup workflow.

The initial estimate is **30-90+ minutes**, not a measured guarantee. Downloads
show byte-based percentages when a content length is available. Builds/readiness
show an activity bar with step names instead of fabricated percentages. Logs in
the UI redact known account secrets. They are not automatically written to disk.
Closing the GUI after completion leaves containers running. Startup validation
does not establish that a complete route can be imported, processed and exported.

Official prerequisite instructions:
https://docs.docker.com/desktop/setup/install/windows-install/
and https://learn.microsoft.com/en-us/windows/wsl/basic-commands.

## Edit and test

Annotation jobs are successful only when every segment has an annotation artifact.
Exports validate segment outputs before being queued and show which segments need
repair. Automatic CVAT annotation tasks use small, disk-backed chunks to avoid
large Redis cache transfers. Export folders and filenames use underscores in
place of the route separator so Windows can extract the archive.

For recovery without rerunning completed segments, copy
`scripts/Repair-Annotation-Job.py` into the `cvat_worker` container and run it
there with `--route`, `--job`, `--run` and `--camera`. It refuses an already
running job and retries only incomplete segments. A successful repair preserves
the existing job number; create a new export afterwards. Previous failed export
records remain available for diagnosis.

Run from the project root in PowerShell:

```powershell
python -m unittest discover -s tests\startup -p test_tkinter_launcher.py -v
python -m unittest discover -s tests\startup -p test_workspace.py -v
powershell -NoProfile -ExecutionPolicy Bypass -File tests\startup\Test-GuiAccount.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tests\startup\Test-Startup.ps1
```

The GUI tests check both switch defaults, field/link visibility, wording,
configuration preservation, the completion page, secret redaction and the
PowerShell account writer with synthetic data. The Compose account test uses
temporary synthetic values and does not start containers. Open a safe GUI preview:

```powershell
python launcher\workspace.py --preview existing
python launcher\workspace.py --preview new
```

Previews use temporary synthetic accounts and disable saving/installation.
For an existing configured installation, `python launcher\workspace.py --smoke-test`
runs the real install/start path and validates native tabs, rendered pages,
account-bridge isolation, CVAT authentication/Tasks, local CVAT link routing,
and upload/download mechanisms with synthetic files. It signs in using saved
CVAT credentials (without printing them), then closes the GUI. It starts services
and applies existing migrations just like normal use. This is not a complete
route ingestion, annotation and dataset export test.

`launcher/Build-Launcher.ps1` rebuilds the small C# EXE entry point if that entry
point itself changes. It is unnecessary when editing the Python/HTML interface.

The generated EXE is currently unsigned. Sign release builds with your team's
code-signing certificate before broad distribution. Windows reputation/policy
checks may apply. Clean-machine WSL/Docker/Git installation and restart recovery
still need verification on a disposable Windows VM; the existing-install startup
path and account serialization were tested on the development computer.
