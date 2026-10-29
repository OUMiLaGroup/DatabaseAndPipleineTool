"""Account isolation and installer behavior, with no Docker changes."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "launcher"))
from workspace import Installer, SetupApi, dashboard_target
from mila_launcher import REQUIRED_CREDENTIALS


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mila-workspace-test-")
        self.root = Path(self.temp.name)
        self.installer = Installer(self.root)
        self.api = SetupApi(self.installer)

    def tearDown(self):
        self.temp.cleanup()

    def save_demo(self):
        self.values = {key: "demo_secret" for key in REQUIRED_CREDENTIALS}
        (self.root / ".env").write_text("\n".join(f"{key}={value}" for key, value in self.values.items()))
        self.installer.saved = self.values

    def test_state_never_contains_account_secrets(self):
        self.save_demo()
        state = self.api.state()
        self.assertTrue(state["configured"])
        self.assertNotIn("demo_secret", str(state))
        self.assertNotIn("saved", state)
        self.assertEqual(self.api.account()["CVAT_PASSWORD"], "[hidden]")
        self.assertEqual(self.api.account(True)["CVAT_PASSWORD"], "demo_secret")
        self.assertEqual(self.api.account("true")["CVAT_PASSWORD"], "[hidden]")

    def test_new_account_cannot_replace_existing_settings(self):
        self.save_demo()
        before = (self.root / ".env").read_bytes()
        with patch("workspace.threading.Thread") as thread:
            self.assertIn("error", self.installer.start("new", {}))
            thread.assert_not_called()
        self.assertEqual((self.root / ".env").read_bytes(), before)

    def test_missing_existing_account_and_preview_cannot_install(self):
        self.assertIn("error", self.installer.start("existing", {}))
        self.installer.preview = True
        self.assertIn("error", self.installer.start("new", {}))
        self.assertFalse(self.installer.running)

    def test_inflight_install_does_not_start_again(self):
        self.save_demo()
        with patch("workspace.threading.Thread") as thread:
            self.assertTrue(self.installer.start("existing", {})["ok"])
            self.assertIn("error", self.installer.start("existing", {}))
            self.assertEqual(thread.call_count, 1)

    def test_logs_redact_secrets_and_use_incremental_cursors(self):
        self.save_demo()
        self.installer.log("password demo_secret")
        first = self.installer.snapshot()
        self.assertEqual(first["logs"], ["password [hidden]"])
        self.assertEqual(self.installer.snapshot(first["cursor"])["logs"], [])
        self.installer.log("DOWNLOAD 30% Docker")
        state = self.installer.snapshot(first["cursor"])
        self.assertEqual(state["progress"], 30)
        self.assertEqual(state["logs"], ["DOWNLOAD 30% Docker"])

    def test_only_explicit_dashboard_origins_route_into_tabs(self):
        self.assertEqual(dashboard_target("http://localhost:8080/tasks/123"), "cvat")
        self.assertEqual(dashboard_target("http://localhost:5173/routes"), "mila")
        for url in ("https://example.com", "http://localhost:8080.evil.test/", "http://localhost:1234",
                    "http://localhost:8080@evil.test", "file:///etc/passwd", "javascript:alert(1)"):
            self.assertIsNone(dashboard_target(url))


if __name__ == "__main__":
    unittest.main()
