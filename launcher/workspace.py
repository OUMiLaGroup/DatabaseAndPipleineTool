"""One Windows workspace with isolated native WebView2 dashboard tabs."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen
import webbrowser

from mila_launcher import PROJECT_ROOT, REQUIRED_CREDENTIALS, create_account, has_credentials, powershell_script, read_account, redact

URLS = {"mila": "http://localhost:5173", "cvat": "http://localhost:8080"}
PROBES = {"mila": "http://localhost:5173", "cvat": "http://localhost:8080/api/server/about"}
HELP = {"comma": "https://jwt.comma.ai", "minio": "https://www.min.io/download"}


def dashboard_target(url: str) -> str | None:
    """Only route the two explicit local dashboard origins to embedded tabs."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname != "localhost" or parsed.username or parsed.password:
            return None
        return {5173: "mila", 8080: "cvat"}.get(parsed.port)
    except ValueError:
        return None


class Installer:
    def __init__(self, root: Path, *, preview=False):
        self.root = root
        self.preview = preview
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.running = False
        self.complete = False
        self.code = None
        self.logs: list[tuple[int, str]] = []
        self.sequence = 0
        self.status = "Ready when you are."
        self.progress = None
        self.ready = {key: False for key in URLS}
        self.saved = read_account(root / ".env")
        self.on_complete = lambda: None

    def snapshot(self, cursor=0):
        with self.lock:
            return {"configured": has_credentials(self.saved), "running": self.running,
                    "complete": self.complete, "code": self.code, "status": self.status,
                    "progress": self.progress, "ready": dict(self.ready), "cursor": self.sequence,
                    "logs": [line for seq, line in self.logs if seq > int(cursor)],
                    "license": str(self.root / "minio/minio.license") if (self.root / "minio/minio.license").is_file() else ""}

    def log(self, line):
        import re
        with self.lock:
            line = redact(line, self.saved)
            self.sequence += 1
            self.logs.append((self.sequence, line))
            self.logs = self.logs[-1200:]
            download = re.match(r"DOWNLOAD (\d+)% (.+)", line)
            step = re.match(r"\[(\d)/5\] (.+)", line)
            if download:
                self.progress = min(100, int(download[1]))
                self.status = f"Downloading {download[2]}: {download[1]}%"
            elif step:
                self.progress = None
                self.status = f"Step {step[1]} of 5: {step[2]}"
            elif re.match(r"Preparing|Downloading|Installing|Updating|Follow|Complete|Waiting|Finding|Checking", line):
                self.progress = None
                self.status = line

    def start(self, mode, details):
        with self.lock:
            if self.preview:
                return {"error": "Preview mode does not install or save anything."}
            if self.running:
                return {"error": "Setup is already running."}
            if mode not in ("existing", "new"):
                return {"error": "Choose Existing Account or New Account."}
            self.saved = read_account(self.root / ".env")
            if mode == "existing" and not has_credentials(self.saved):
                return {"error": "No saved credentials were detected. Choose New Account first."}
            if mode == "new" and (self.root / ".env").exists():
                return {"error": "This project already has saved account settings. Use Existing Account here, or a fresh project folder to set up a New Account."}
            if mode == "new" and details.get("password") != details.get("confirm"):
                return {"error": "Passwords do not match."}
            self.running = True
            self.complete = False
            self.code = None
            self.status = "Checking prerequisites..."
            self.progress = None
            self.logs.clear()
            threading.Thread(target=self._run, args=(mode, dict(details)), daemon=True).start()
            return {"ok": True}

    def _run(self, mode, details):
        try:
            if mode == "new":
                create_account(self.root, details.get("username", ""), details.get("password", ""),
                               details.get("token", ""), details.get("license", ""))
                with self.lock:
                    self.saved = read_account(self.root / ".env")
            process = subprocess.Popen(powershell_script(self.root / "launcher/Install-Components.ps1"),
                                       cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in process.stdout:
                self.log(line.rstrip())
            process.stdout.close()
            code = process.wait()
        except (OSError, ValueError) as error:
            self.log(f"Setup stopped: {error}")
            code = 1
        finally:
            details.clear()
        with self.lock:
            self.running = False
            self.code = code
            self.complete = code == 0
            self.progress = 100 if code == 0 else 0
            self.status = "MiLa is running. Open the MiLa or CVAT tab." if code == 0 else "Setup stopped. Read the message below, resolve it, then retry."
        if code == 0:
            self.on_complete()


class SetupApi:
    """Exposed ONLY in the local Account/Setup document, never dashboard pages."""
    def __init__(self, installer: Installer):
        self._installer = installer
        self._host = None

    def state(self, cursor=0):
        return self._installer.snapshot(cursor)

    def start_install(self, mode, details):
        return self._installer.start(mode, details)

    def account(self, reveal=False):
        from mila_launcher import SECRET_KEY
        saved = read_account(self._installer.root / ".env")
        return {key: value if reveal is True or not SECRET_KEY.search(key) else "[hidden]" for key, value in saved.items()}

    def choose_license(self):
        import webview
        paths = self._host.window.create_file_dialog(webview.FileDialog.OPEN,
                                                    file_types=("License files (*.license)", "All files (*.*)"))
        return paths[0] if paths else ""

    def open_help(self, kind):
        if kind in HELP:
            webbrowser.open(HELP[kind])

    def select_tab(self, kind):
        if kind in URLS:
            self._host.select_tab(kind)


class Workspace:
    """Native tabs contain three separate top-level browser documents (no iframe)."""
    def __init__(self, root: Path, *, preview=False, trace=False):
        import webview
        self.trace = trace
        self.installer = Installer(root, preview=preview)
        self.api = SetupApi(self.installer)
        self.api._host = self
        self.closed = self.installer.stopped
        self.mounted = threading.Event()
        self.remote_initialized = {key: threading.Event() for key in URLS}
        self.remotes = {}
        self.browser_layouts = {}
        self.navigation_icons = []
        self.loaded = set()
        self.pages = {}
        self.handlers = []
        self.tabs = None
        self.window = webview.create_window(
            "MiLa workspace", html=(PROJECT_ROOT / "launcher/workspace.html").read_text(encoding="utf-8"),
            js_api=self.api, width=1200, height=850, min_size=(850, 650), background_color="#f5f7fb", text_select=True,
        )
        self.window.events.closing += self._closing
        self.window.events.closed += lambda: self.closed.set()
        self.installer.on_complete = self._started

    def ui(self, callback):
        from System import Action
        if self.window.native.IsDisposed:
            return
        if self.window.native.InvokeRequired:
            self.window.native.Invoke(Action(callback))
        else:
            callback()

    def mount(self):
        if self.trace: print('Checking local setup browser...', flush=True)
        if not self.window.events.loaded.wait(45):
            raise RuntimeError("Account/Setup did not load in WebView2.")
        if self.trace: print('Mounting native dashboard tabs...', flush=True)
        self.ui(self._mount_native)
        if self.trace: print('Native tabs mounted.', flush=True)
        self.mounted.set()
        threading.Thread(target=self._monitor, daemon=True).start()

    def _mount_native(self):
        from System import Uri
        from System.Drawing import Font, Size
        from System.Windows.Forms import (DockStyle, TabControl, TabPage, Panel, Button, Label,
                                          TableLayoutPanel, RowStyle, SizeType, Padding, FlatStyle, ToolTip)
        from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties

        native = self.window.native
        local = native.webview
        # The privileged setup browser never navigates to dashboard/remote content.
        def local_navigation(sender, args):
            if args.Uri != "about:blank":
                args.Cancel = True
        local.NavigationStarting += local_navigation
        self.handlers.append(local_navigation)
        self.tabs = TabControl()
        self.tabs.Dock = DockStyle.Fill
        self.tabs.Font = Font("Segoe UI", 11)
        self.tabs.ItemSize = Size(170, 34)
        for kind, name in (("setup", "Account / Setup"), ("mila", "MiLa Dashboard"), ("cvat", "CVAT")):
            page = TabPage(name)
            self.pages[kind] = page
            self.tabs.TabPages.Add(page)
        native.Controls.Remove(local)
        self.pages["setup"].Controls.Add(local)
        local.Dock = DockStyle.Fill
        native.Controls.Add(self.tabs)
        self.tabs.BringToFront()

        for kind in URLS:
            control = WebView2()
            properties = CoreWebView2CreationProperties()
            properties.UserDataFolder = local.CreationProperties.UserDataFolder
            properties.AdditionalBrowserArguments = local.CreationProperties.AdditionalBrowserArguments
            properties.set_IsInPrivateModeEnabled(False)
            control.CreationProperties = properties
            control.Dock = DockStyle.Fill
            # Keep browser navigation controls outside the web page.
            toolbar = Panel()
            toolbar.Dock = DockStyle.Top
            toolbar.Height = 42
            tooltip = ToolTip()
            self.handlers.append(tooltip)
            for index, (text, operation) in enumerate((("Back", "back"), ("Forward", "forward"), ("Reload", "reload"))):
                button = Button()
                button.Text = ''
                button.AccessibleName = text
                button.Image = self._navigation_icon(operation)
                self.navigation_icons.append(button.Image)
                button.FlatStyle = FlatStyle.Flat
                button.FlatAppearance.BorderSize = 0
                button.Left = 8 + index * 38
                button.Top = 4
                button.Width = 34
                button.Height = 34
                tooltip.SetToolTip(button, text)
                handler = lambda sender, args, k=kind, op=operation: self._navigate(k, op)
                button.Click += handler
                self.handlers.append(handler)
                toolbar.Controls.Add(button)
            label = Label()
            label.Text = URLS[kind]
            label.Left = 132
            label.Top = 12
            label.Width = 300
            toolbar.Controls.Add(label)
            # Separate rows reserve space for the toolbar; native WebView2 must
            # not share a Fill-docked region underneath a top-docked overlay.
            layout = TableLayoutPanel()
            layout.Dock = DockStyle.Fill
            layout.ColumnCount = 1
            layout.RowCount = 2
            layout.Margin = Padding(0)
            layout.Padding = Padding(0)
            layout.RowStyles.Add(RowStyle(SizeType.Absolute, 42))
            layout.RowStyles.Add(RowStyle(SizeType.Percent, 100))
            toolbar.Dock = DockStyle.Fill
            toolbar.Margin = Padding(0)
            control.Margin = Padding(0)
            layout.Controls.Add(toolbar, 0, 0)
            layout.Controls.Add(control, 0, 1)
            self.pages[kind].Controls.Add(layout)
            self.browser_layouts[kind] = (layout, toolbar)
            self.remotes[kind] = control
            initialized = lambda sender, args, k=kind: self._browser_ready(k, args)
            control.CoreWebView2InitializationCompleted += initialized
            self.handlers.append(initialized)
            # Inactive TabPages are hidden: explicitly create the HWND so the
            # browser can initialize before the user first selects the tab.
            control.CreateControl()
            _ = control.Handle
            control.EnsureCoreWebView2Async(None)

    @staticmethod
    def _navigation_icon(operation):
        from System import Array
        from System.Drawing import Bitmap, Graphics, Pen, SolidBrush, Color, Point
        from System.Drawing.Drawing2D import SmoothingMode, LineCap
        icon = Bitmap(24, 24)
        graphics = Graphics.FromImage(icon)
        graphics.SmoothingMode = SmoothingMode.AntiAlias
        color = Color.FromArgb(52, 64, 84)
        pen = Pen(color, 2.0)
        pen.StartCap = pen.EndCap = LineCap.Round
        try:
            if operation in ('back', 'forward'):
                tip, tail, bend = (6, 18, 11) if operation == 'back' else (18, 6, 13)
                graphics.DrawLine(pen, tail, 12, tip, 12)
                graphics.DrawLine(pen, tip, 12, bend, 7)
                graphics.DrawLine(pen, tip, 12, bend, 17)
            else:
                graphics.DrawArc(pen, 5, 5, 14, 14, 45, 270)
                brush = SolidBrush(color)
                try:
                    graphics.FillPolygon(brush, Array[Point]([Point(19, 10), Point(13, 7), Point(18, 3)]))
                finally:
                    brush.Dispose()
        finally:
            pen.Dispose()
            graphics.Dispose()
        return icon

    def _browser_ready(self, kind, args):
        if self.trace: print(f'{kind} WebView initialization: {args.IsSuccess}', flush=True)
        if not args.IsSuccess:
            self.installer.log(f"{kind} browser could not initialize: {args.InitializationException}")
            return
        core = self.remotes[kind].CoreWebView2
        core.Settings.IsScriptEnabled = True
        # Remote pages have no native message bridge or host objects.
        core.Settings.IsWebMessageEnabled = False
        core.Settings.AreHostObjectsAllowed = False
        new_window = lambda sender, event, k=kind: self._popup(k, event)
        download = lambda sender, event: self._download(event)
        def navigation(sender, event, k=kind):
            if not event.IsSuccess and str(event.WebErrorStatus) != 'OperationCanceled':
                self.installer.log(f'{k} page load failed: {event.WebErrorStatus}. Retrying when its service is ready.')
                self.loaded.discard(k)
        core.NewWindowRequested += new_window
        core.DownloadStarting += download
        core.NavigationCompleted += navigation
        self.handlers.extend((new_window, download, navigation))
        core.NavigateToString("<html><body style='font:18px Segoe UI;padding:35px;color:#152138'>"
                              "<h2>Start your workspace</h2><p>Use Account / Setup to start the services. "
                              "This tab will load automatically when its dashboard is ready.</p></body></html>")
        self.remote_initialized[kind].set()

    def _navigate(self, kind, operation):
        core = self.remotes[kind].CoreWebView2
        if core is None:
            return
        if operation == "back" and core.CanGoBack:
            core.GoBack()
        elif operation == "forward" and core.CanGoForward:
            core.GoForward()
        elif operation == "reload":
            # Browser reload only; it never restarts a container.
            if kind in self.loaded:
                core.Reload()

    def _popup(self, kind, args):
        args.Handled = True
        target = dashboard_target(args.Uri)
        if target and self.remotes[target].CoreWebView2:
            self.remotes[target].CoreWebView2.Navigate(args.Uri)
            self.loaded.add(target)
            self.tabs.SelectedTab = self.pages[target]
        elif urlsplit(args.Uri).scheme in ("http", "https"):
            webbrowser.open(args.Uri)

    def _download(self, args):
        from System.Windows.Forms import SaveFileDialog, DialogResult
        # Only the explicit --smoke-test runner sets this disposable destination.
        if getattr(self, "_smoke_download_path", None):
            args.ResultFilePath = self._smoke_download_path
            args.Handled = True
            return
        dialog = SaveFileDialog()
        dialog.FileName = Path(args.ResultFilePath).name
        dialog.Title = "Save dashboard download"
        if dialog.ShowDialog(self.window.native) == DialogResult.OK:
            args.ResultFilePath = dialog.FileName
            args.Handled = True
        else:
            args.Cancel = True
        dialog.Dispose()

    def _monitor(self):
        while not self.closed.is_set():
            if not self.installer.preview:
                for kind, probe in PROBES.items():
                    try:
                        with urlopen(probe, timeout=3) as response:
                            ready = response.status == 200
                    except OSError:
                        ready = False
                    with self.installer.lock:
                        self.installer.ready[kind] = ready
                    if ready and kind not in self.loaded and self.remote_initialized[kind].is_set():
                        def load(k=kind):
                            self.remotes[k].CoreWebView2.Navigate(URLS[k])
                            self.loaded.add(k)
                        self.ui(load)
            self.closed.wait(5)

    def select_tab(self, kind):
        if self.mounted.is_set():
            self.ui(lambda: setattr(self.tabs, "SelectedTab", self.pages[kind]))

    def _started(self):
        self.select_tab("mila")

    def _closing(self):
        if self.installer.running:
            from System.Windows.Forms import MessageBox
            MessageBox.Show("Setup is still running. Keep this window open until it finishes.", "Setup in progress")
            return False
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--preview", choices=("existing", "new"))
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("The integrated workspace currently requires Windows and WebView2.")
    if args.preview and args.smoke_test:
        parser.error("Choose preview or smoke test.")
    temporary = tempfile.TemporaryDirectory(prefix="mila-workspace-preview-", ignore_cleanup_errors=True) if args.preview else None
    root = Path(temporary.name) if temporary else args.root.resolve()
    if args.preview == "existing":
        (root / ".env").write_text("\n".join(f"{key}=demo_value" for key in REQUIRED_CREDENTIALS), encoding="utf-8")
    mutex = None
    try:
        import webview
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        name = "Local\\MiLaSetup-" + hashlib.sha256(str(root).lower().encode()).hexdigest()
        mutex = kernel.CreateMutexW(None, False, name)
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            from tkinter import messagebox
            messagebox.showinfo("MiLa", "MiLa is already open for this project. Use the existing window.")
            return 1
        profile = Path(os.environ["LOCALAPPDATA"]) / "MiLa/BrowserProfiles" / hashlib.sha256(str(root).lower().encode()).hexdigest()[:16]
        if temporary:
            profile = root / "browser-profile"
        profile.mkdir(parents=True, exist_ok=True)
        webview.settings["ALLOW_FILE_URLS"] = False
        host = Workspace(root, preview=bool(args.preview), trace=args.smoke_test)
        result = [0]

        def initialize():
            if args.smoke_test:
                import faulthandler
                faulthandler.dump_traceback_later(120, repeat=False)
            try:
                host.mount()
                if args.smoke_test:
                    from workspace_smoke import run_smoke
                    run_smoke(host)
                    print("PASS: native dashboard tabs, rendering, account isolation, CVAT authentication and startup.")
                    faulthandler.cancel_dump_traceback_later()
                    host.window.destroy()
            except Exception as error:
                result[0] = 1
                print(f"MiLa workspace: {error}")
                if args.smoke_test:
                    faulthandler.cancel_dump_traceback_later()
                    for _, line in host.installer.logs:
                        print(line)
                    host.window.destroy()
                else:
                    host.window.create_confirmation_dialog("MiLa workspace", f"Unable to initialize the dashboard tabs: {error}")

        webview.start(initialize, gui="edgechromium", private_mode=False, storage_path=str(profile))
        return result[0]
    except Exception as error:
        from tkinter import messagebox
        messagebox.showerror("MiLa workspace", "Unable to open the embedded workspace. Install Microsoft Edge WebView2 Runtime "
                             "and launcher/requirements.txt, then retry.\n\n" + str(error))
        return 1
    finally:
        if mutex:
            kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
            kernel.CloseHandle(mutex)
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
