"""Editable Tkinter interface for MiLa's PowerShell installation workflow."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import webbrowser

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXISTING = "Existing Account"
NEW = "New Account"
REMEMBERED = "Your account information will be remembered and pre-loaded next time you run this application."
REQUIRED_CREDENTIALS = (
    "POSTGRES_USER", "POSTGRES_PASSWORD", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD",
    "COMMA_JWT", "CVAT_EMAIL", "CVAT_PASSWORD",
)
SECRET_KEY = re.compile(r"PASSWORD|JWT|TOKEN|SECRET", re.I)
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
BG = "#f5f7fb"
BLUE = "#2353be"
INK = "#152138"


def read_account(path: Path) -> dict[str, str]:
    """Read values for display; Compose remains the authority for validation."""
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"\s*([A-Z_]+)\s*=(.*)$", line)
        if not match:
            continue
        key, value = match.groups()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            try:
                value = json.loads(value).replace("$$", "$")
            except json.JSONDecodeError:
                value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("\\'", "'")
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key] = value
    return values


def has_credentials(values: dict[str, str]) -> bool:
    placeholders = {"fill this out", "changeme", "change_me", "your_password", "your_token"}
    return all(values.get(key, "").strip() and values[key].strip().lower() not in placeholders
               for key in REQUIRED_CREDENTIALS)


def redact(line: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        if SECRET_KEY.search(key) and len(value) > 2:
            # Include the escaped representation emitted by configuration tooling.
            variants = (value, json.dumps(value, ensure_ascii=False)[1:-1], value.replace("$", "$$"))
            for variant in sorted(variants, key=len, reverse=True):
                line = line.replace(variant, "[hidden]")
    return JWT_PATTERN.sub("[JWT hidden]", line)


def powershell_script(script: Path) -> list[str]:
    powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]


def create_account(root: Path, username: str, password: str, token: str, license_path: str) -> None:
    """Send secrets over stdin to the existing, tested account writer."""
    payload = json.dumps({"root": str(root), "username": username, "password": password,
                          "token": token.strip(), "license": license_path}, ensure_ascii=False)
    result = subprocess.run(
        powershell_script(PROJECT_ROOT / "launcher/Save-Account.ps1"), input=payload,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )
    if result.returncode:
        raise ValueError(result.stdout.strip() or "Account setup failed. Check the entered details.")


class AccountToggle(tk.Frame):
    """Two-position switch with keyboard-accessible radio button semantics."""
    def __init__(self, parent, variable: tk.StringVar):
        super().__init__(parent, bg="#e4e9f2", padx=3, pady=3)
        self.buttons = []
        for index, mode in enumerate((EXISTING, NEW)):
            button = tk.Radiobutton(
                self, text=mode, variable=variable, value=mode, indicatoron=False,
                width=19, padx=12, pady=9, relief="flat", borderwidth=0,
                bg="#e4e9f2", fg=INK, selectcolor=BLUE, activebackground="#d3ddf0",
                font=("Segoe UI", 10, "bold"), cursor="hand2", takefocus=True,
            )
            button.grid(row=0, column=index, sticky="ew")
            self.buttons.append(button)
        self.variable = variable
        variable.trace_add("write", self._refresh)
        self._refresh()

    def _refresh(self, *_):
        for button, mode in zip(self.buttons, (EXISTING, NEW)):
            button.configure(fg="white" if self.variable.get() == mode else INK)

    def set_enabled(self, enabled: bool):
        for button in self.buttons:
            button.configure(state="normal" if enabled else "disabled")


class MilaLauncher:
    def __init__(self, window: tk.Tk, root: Path = PROJECT_ROOT, *, preview=False, smoke_test=False):
        self.window, self.root = window, root
        self.preview, self.smoke_test = preview, smoke_test
        self.saved = read_account(root / ".env")
        self.configured = has_credentials(self.saved)
        self.running = False
        self.completed = False
        self.result_code = 0
        self.events: queue.Queue = queue.Queue()
        self.process = None
        self.mode = tk.StringVar(value=EXISTING if self.configured else NEW)
        self.fields = {key: tk.StringVar() for key in ("username", "password", "confirm", "token", "license")}
        if (root / "minio/minio.license").is_file():
            self.fields["license"].set(str(root / "minio/minio.license"))

        window.title("MiLa | Installation & startup")
        window.geometry(f"840x{min(800, window.winfo_screenheight() - 100)}")
        window.minsize(760, 560)
        window.configure(bg=BG)
        window.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(window)
        style.theme_use("clam")
        style.configure("MiLa.TFrame", background=BG)
        style.configure("MiLa.Horizontal.TProgressbar", background=BLUE, troughcolor="#e4e9f2", borderwidth=0)
        style.configure("TEntry", padding=6)

        shell = ttk.Frame(window, style="MiLa.TFrame")
        shell.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(shell, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.page = tk.Frame(self.canvas, bg=BG, padx=28, pady=22)
        self.page_id = self.canvas.create_window((0, 0), window=self.page, anchor="nw")
        self.page.columnconfigure(0, weight=1)
        self.page.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize)
        window.bind("<MouseWheel>", self._scroll)

        self.title = self.label(self.page, "MiLa setup", size=25, bold=True)
        self.title.grid(row=0, sticky="w", pady=(0, 10))
        self.subtitle = self.label(self.page, "")
        self.subtitle.grid(row=1, sticky="ew", pady=(0, 15))
        self.toggle = AccountToggle(self.page, self.mode)
        self.toggle.grid(row=2, sticky="w", pady=(0, 12))
        self.account_link = self.link(self.page, "Account - view saved credentials", self.show_account)
        self.account_link.grid(row=3, sticky="w", pady=(0, 12))
        self.remembered = self.label(self.page, REMEMBERED)
        self.remembered.grid(row=4, sticky="ew", pady=(0, 15))

        # All new-account fields and help links live in one frame, so switching
        # to Existing Account removes them from both layout and keyboard focus.
        self.new_account = tk.Frame(self.page, bg=BG)
        self.new_account.grid(row=5, sticky="ew", pady=(0, 12))
        self.new_account.columnconfigure(1, weight=1)
        self.entries = []
        for row, (caption, key, secret) in enumerate((
            ("Shared username", "username", False), ("Shared password", "password", True),
            ("Confirm password", "confirm", True), ("Comma AI JWT", "token", True),
            ("MinIO license file", "license", False),
        )):
            self.label(self.new_account, caption).grid(row=row, column=0, sticky="w", padx=(0, 18), pady=5)
            entry = ttk.Entry(self.new_account, textvariable=self.fields[key], show="*" if secret else "")
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            if key == "license":
                entry.configure(state="readonly")
            self.entries.append(entry)
        self.browse = ttk.Button(self.new_account, text="Choose license file...", command=self.browse_license)
        self.browse.grid(row=5, column=1, sticky="w", pady=(4, 12))
        self.new_help = self.label(
            self.new_account,
            "Use the same username and password for PostgreSQL, MinIO and CVAT. "
            "CVAT email is username@mila.local. Use a password with 12+ characters.",
        )
        self.new_help.grid(row=6, columnspan=2, sticky="ew", pady=(0, 8))
        self.jwt_link = self.link(self.new_account, "Get Comma JWT: sign in at jwt.comma.ai with your driving-data account.",
                                  lambda: webbrowser.open("https://jwt.comma.ai"))
        self.jwt_link.grid(row=7, columnspan=2, sticky="w", pady=4)
        self.minio_link = self.link(self.new_account, "Get the separate MinIO AIStor license from your administrator or MinIO.",
                                    lambda: webbrowser.open("https://www.min.io/download"))
        self.minio_link.grid(row=8, columnspan=2, sticky="w", pady=4)

        self.estimate = self.label(
            self.page, "Estimated first setup: 30-90+ minutes; an existing setup usually takes 1-5 minutes. "
            "Downloads and builds depend on network and CPU. Windows/Docker may request approval, terms acceptance or a restart.",
        )
        self.estimate.grid(row=6, sticky="ew", pady=(0, 14))
        self.install_button = tk.Button(
            self.page, text="Install necessary components", command=self.start,
            font=("Segoe UI", 11, "bold"), bg=BLUE, fg="white", activebackground="#183f96",
            activeforeground="white", relief="flat", padx=22, pady=11, cursor="hand2",
        )
        self.install_button.grid(row=7, sticky="w", pady=(0, 12))
        self.status = tk.StringVar(value="Ready when you are.")
        self.status_label = self.label(self.page, "", variable=self.status)
        self.status_label.grid(row=8, sticky="ew", pady=(0, 9))
        self.progress = ttk.Progressbar(self.page, style="MiLa.Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.progress.grid(row=9, sticky="ew", pady=(0, 12))
        self.log = scrolledtext.ScrolledText(self.page, height=8, font=("Consolas", 9), wrap="word",
                                           relief="flat", borderwidth=1, state="disabled")
        self.log.grid(row=10, sticky="ew", pady=(0, 12))
        self.workspace_links = tk.Frame(self.page, bg=BG)
        self.link(self.workspace_links, "Open MiLa dashboard  http://localhost:5173",
                  lambda: webbrowser.open("http://localhost:5173")).pack(anchor="w", pady=4)
        self.link(self.workspace_links, "Open CVAT  http://localhost:8080",
                  lambda: webbrowser.open("http://localhost:8080")).pack(anchor="w", pady=4)

        self.mode.trace_add("write", self.update_mode)
        self.update_mode()
        if smoke_test:
            if not self.configured:
                raise ValueError("Smoke test requires an existing configured installation.")
            window.after(200, self.start)

    @staticmethod
    def label(parent, text, *, size=10, bold=False, variable=None):
        return tk.Label(parent, text=text, textvariable=variable, bg=BG, fg=INK,
                        justify="left", anchor="w", wraplength=740,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    @staticmethod
    def link(parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=BG, fg=BLUE,
                         activebackground=BG, activeforeground="#183f96", borderwidth=0,
                         relief="flat", padx=0, pady=0, cursor="hand2",
                         font=("Segoe UI", 10, "underline"), anchor="w", wraplength=740, justify="left")

    def _resize(self, event):
        self.canvas.itemconfigure(self.page_id, width=event.width)
        for widget in (self.subtitle, self.remembered, self.new_help, self.estimate,
                       self.status_label, self.jwt_link, self.minio_link):
            widget.configure(wraplength=max(300, event.width - 60))

    def _scroll(self, event):
        if self.canvas.bbox("all") and self.canvas.bbox("all")[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def update_mode(self, *_):
        self.account_link.configure(state="normal" if self.configured else "disabled")
        if self.completed:
            return
        if self.mode.get() == EXISTING:
            self.new_account.grid_remove()
            self.remembered.grid()
            self.subtitle.configure(text=(
                "Existing configuration found. Open Account link below to view it, or start your workspace."
                if self.configured else "Choose New Account to enter your account information."
            ))
            self.install_button.configure(text="Check components and start MiLa", state="normal" if self.configured else "disabled")
        else:
            self.new_account.grid()
            self.remembered.grid_remove()
            self.subtitle.configure(text="Set up your account, install the components, then open your workspace.")
            self.install_button.configure(text="Install necessary components", state="normal")

    def browse_license(self):
        path = filedialog.askopenfilename(parent=self.window, title="Choose MinIO license",
                                         filetypes=(("License files", "*.license"), ("All files", "*.*")))
        if path:
            self.fields["license"].set(path)

    def show_account(self):
        saved = read_account(self.root / ".env")
        dialog = tk.Toplevel(self.window)
        dialog.title("MiLa account")
        dialog.geometry("740x540")
        dialog.configure(bg=BG)
        dialog.transient(self.window)
        dialog.grab_set()
        self.label(dialog, REMEMBERED).pack(fill="x", padx=20, pady=15)
        reveal = tk.BooleanVar(value=False)
        text = scrolledtext.ScrolledText(dialog, font=("Consolas", 10), wrap="none", state="disabled")

        def refresh():
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("end", "\n".join(f"{key}={value if reveal.get() or not SECRET_KEY.search(key) else '[hidden]'}"
                                         for key, value in saved.items()))
            text.configure(state="disabled")

        ttk.Checkbutton(dialog, text="Show passwords and Comma token", variable=reveal,
                        command=refresh).pack(anchor="w", padx=20, pady=(0, 12))
        text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        refresh()

    def start(self):
        if self.running:
            return
        try:
            if self.preview:
                raise ValueError("Preview mode does not install or save anything.")
            if self.mode.get() == NEW:
                if (self.root / ".env").exists():
                    raise ValueError("This project already has saved account settings. Use Existing Account here, "
                                     "or a fresh project folder to set up a New Account.")
                if self.fields["password"].get() != self.fields["confirm"].get():
                    raise ValueError("Passwords do not match.")
                create_account(self.root, self.fields["username"].get(), self.fields["password"].get(),
                               self.fields["token"].get(), self.fields["license"].get())
                self.saved = read_account(self.root / ".env")
                self.configured = has_credentials(self.saved)
                self.mode.set(EXISTING)
            elif not self.configured:
                raise ValueError("No saved credentials were detected. Choose New Account first.")
            self.saved = read_account(self.root / ".env")
            self.running = True
            self.toggle.set_enabled(False)
            self.install_button.configure(state="disabled")
            self.status.set("Checking prerequisites...")
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.configure(state="disabled")
            threading.Thread(target=self.run_installer, daemon=True).start()
            self.window.after(100, self.poll)
        except (OSError, ValueError) as error:
            if self.smoke_test:
                print(str(error))
                self.result_code = 1
                self.window.destroy()
            else:
                messagebox.showerror("MiLa setup", str(error), parent=self.window)

    def run_installer(self):
        try:
            self.process = subprocess.Popen(
                powershell_script(self.root / "launcher/Install-Components.ps1"), cwd=self.root,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for line in self.process.stdout:
                self.events.put(("line", redact(line.rstrip(), self.saved)))
            self.process.stdout.close()
            self.events.put(("done", self.process.wait()))
        except OSError as error:
            self.events.put(("line", f"Unable to start installer: {error}"))
            self.events.put(("done", 1))

    def append_log(self, line: str):
        self.log.configure(state="normal")
        if int(self.log.index("end-1c").split(".")[0]) > 1200:
            self.log.delete("1.0", "400.0")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        download = re.match(r"DOWNLOAD (\d+)% (.+)$", line)
        step = re.match(r"\[(\d)/5\] (.+)$", line)
        if download:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=min(100, int(download[1])))
            self.status.set(f"Downloading {download[2]}: {download[1]}%")
        elif step or re.match(r"Preparing|Downloading|Installing|Updating|Follow|Complete|Waiting|Finding|Checking", line):
            self.progress.stop()
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
            self.status.set(f"Step {step[1]} of 5: {step[2]}" if step else line)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "line":
                    self.append_log(value)
                else:
                    self.finish(value)
                    if self.smoke_test:
                        return
        except queue.Empty:
            pass
        if self.running:
            self.window.after(100, self.poll)

    def finish(self, code: int):
        self.running = False
        self.result_code = code
        self.progress.stop()
        self.progress.configure(mode="determinate", value=100 if code == 0 else 0)
        self.install_button.configure(state="normal")
        self.toggle.set_enabled(True)
        if code == 0:
            self.completed = True
            self.title.configure(text="Your MiLa workspace")
            self.subtitle.configure(text="Startup checks passed. Open the dashboard or CVAT below.")
            self.status.set("MiLa is running. Your workspace is ready.")
            self.toggle.grid_remove()
            self.new_account.grid_remove()
            self.estimate.grid_remove()
            self.remembered.grid()
            self.workspace_links.grid(row=11, sticky="w")
            self.install_button.configure(text="Check and start again")
            self.append_log("Next: validate a complete route import, annotation and export. "
                            "Containers keep running after you close this app.")
        else:
            self.status.set("Setup stopped. Read the message below, resolve it, then retry.")
            self.install_button.configure(text="Retry setup")
        if self.smoke_test:
            print(self.log.get("1.0", "end-1c"))
            self.window.destroy()

    def close(self):
        if self.running:
            messagebox.showinfo("Setup in progress", "Setup is still running. Keep this window open until it finishes. "
                                "Docker or Git may be waiting in their installer windows.", parent=self.window)
        else:
            self.window.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--preview", choices=("existing", "new"), help="Use synthetic data; never save or install.")
    parser.add_argument("--smoke-test", action="store_true", help="Start the configured project and close after completion.")
    args = parser.parse_args()
    if args.preview and args.smoke_test:
        parser.error("Choose preview or smoke test.")
    temporary = tempfile.TemporaryDirectory(prefix="mila-ui-preview-") if args.preview else None
    root = Path(temporary.name) if temporary else args.root.resolve()
    if args.preview == "existing":
        values = {key: "demo_value" for key in REQUIRED_CREDENTIALS}
        values.update(POSTGRES_USER="mila_demo", CVAT_EMAIL="mila_demo@mila.local")
        (root / ".env").write_text("\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8")
    mutex = None
    window = None
    try:
        if sys.platform == "win32" and not args.preview:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
            kernel.CreateMutexW.restype = ctypes.c_void_p
            name = "Local\\MiLaSetup-" + hashlib.sha256(str(root).lower().encode()).hexdigest()
            mutex = kernel.CreateMutexW(None, False, name)
            if not mutex:
                raise ctypes.WinError(ctypes.get_last_error())
            if ctypes.get_last_error() == 183:
                messagebox.showinfo("MiLa setup", "MiLa setup is already open for this project. Use the existing window.")
                return 1
        window = tk.Tk()
        app = MilaLauncher(window, root, preview=bool(args.preview), smoke_test=args.smoke_test)
        window.mainloop()
        return app.result_code
    except Exception as error:
        if args.smoke_test:
            print(f"MiLa setup: {error}")
        else:
            messagebox.showerror("Unable to open MiLa", str(error), parent=window)
        return 1
    finally:
        if mutex:
            kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
            kernel.CloseHandle(mutex)
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
