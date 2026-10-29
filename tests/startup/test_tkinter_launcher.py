"""GUI behavior checks using synthetic accounts and temporary project folders."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mila_launcher", ROOT / "launcher/mila_launcher.py")
launcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = launcher
spec.loader.exec_module(launcher)


class TkinterLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mila-tk-test-")
        self.project = Path(self.temp.name)
        self.window = tk.Tk()

    def tearDown(self):
        self.window.update_idletasks()
        self.window.destroy()
        self.temp.cleanup()

    def save_demo(self):
        values = {key: "demo_value" for key in launcher.REQUIRED_CREDENTIALS}
        values["POSTGRES_USER"] = "mila_demo"
        (self.project / ".env").write_text("\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8")

    def test_existing_default_hides_inputs_and_links_and_toggle_restores_them(self):
        self.save_demo()
        app = launcher.MilaLauncher(self.window, self.project, preview=True)
        self.window.update()
        self.assertEqual(app.mode.get(), launcher.EXISTING)
        self.assertFalse(app.new_account.winfo_ismapped())
        self.assertFalse(app.jwt_link.winfo_ismapped())
        self.assertFalse(app.minio_link.winfo_ismapped())
        self.assertTrue(all(not entry.winfo_ismapped() for entry in app.entries))
        self.assertIn("Open Account link below to view it", app.subtitle.cget("text"))
        self.assertEqual(app.remembered.cget("text"), launcher.REMEMBERED)
        self.assertTrue(app.remembered.winfo_ismapped())
        app.mode.set(launcher.NEW)
        self.window.update()
        self.assertTrue(app.new_account.winfo_ismapped())
        self.assertTrue(app.jwt_link.winfo_ismapped())
        self.assertTrue(app.minio_link.winfo_ismapped())
        self.assertTrue(all(entry.winfo_ismapped() for entry in app.entries))
        self.assertFalse(app.remembered.winfo_ismapped())
        app.mode.set(launcher.EXISTING)
        self.window.update()
        self.assertFalse(app.new_account.winfo_ismapped())

    def test_no_credentials_defaults_to_new_and_existing_cannot_start(self):
        app = launcher.MilaLauncher(self.window, self.project, preview=True)
        self.window.update()
        self.assertEqual(app.mode.get(), launcher.NEW)
        self.assertTrue(app.new_account.winfo_ismapped())
        self.assertEqual(app.account_link.cget("state"), "disabled")
        app.mode.set(launcher.EXISTING)
        self.assertEqual(app.install_button.cget("state"), "disabled")

    def test_placeholders_are_not_detected_as_credentials(self):
        (self.project / ".env").write_text("\n".join(f"{key}=fill this out" for key in launcher.REQUIRED_CREDENTIALS))
        app = launcher.MilaLauncher(self.window, self.project)
        self.assertEqual(app.mode.get(), launcher.NEW)

    def test_new_mode_preserves_saved_configuration(self):
        self.save_demo()
        before = (self.project / ".env").read_bytes()
        app = launcher.MilaLauncher(self.window, self.project)
        app.mode.set(launcher.NEW)
        with patch.object(launcher.messagebox, "showerror") as error, patch.object(launcher, "create_account") as create:
            app.start()
            error.assert_called_once()
            create.assert_not_called()
        self.assertEqual((self.project / ".env").read_bytes(), before)

    def test_finished_workspace_contains_links_and_account(self):
        self.save_demo()
        app = launcher.MilaLauncher(self.window, self.project, preview=True)
        app.finish(0)
        self.window.update()
        self.assertTrue(app.workspace_links.winfo_ismapped())
        self.assertTrue(app.account_link.winfo_ismapped())
        self.assertFalse(app.toggle.winfo_ismapped())
        self.assertFalse(app.new_account.winfo_ismapped())
        self.assertEqual(app.progress["value"], 100)

    def test_secret_redaction_and_dotenv_decoding(self):
        password = 'Long$pass"word\\123'
        encoded = json.dumps(password.replace("$", "$$"))
        (self.project / ".env").write_text("POSTGRES_PASSWORD=" + encoded, encoding="utf-8")
        values = launcher.read_account(self.project / ".env")
        self.assertEqual(values["POSTGRES_PASSWORD"], password)
        result = launcher.redact(f"token {password}", values)
        self.assertNotIn(password, result)
        self.assertIn("[hidden]", result)

    @unittest.skipUnless(sys.platform == "win32", "Uses Windows PowerShell")
    def test_fresh_account_uses_existing_writer_and_roundtrips_special_characters(self):
        license_file = self.project / "source.license"
        license_file.write_text("SYNTHETIC TEST LICENSE")
        password = 'Long$pass"word\\123'
        launcher.create_account(self.project, "mila_test", password, "a.b.c", str(license_file))
        saved = launcher.read_account(self.project / ".env")
        self.assertEqual(saved["POSTGRES_PASSWORD"], password)
        self.assertEqual(saved["MINIO_ROOT_PASSWORD"], password)
        self.assertEqual(saved["CVAT_PASSWORD"], password)
        self.assertEqual(saved["CVAT_EMAIL"], "mila_test@mila.local")


if __name__ == "__main__":
    unittest.main()
