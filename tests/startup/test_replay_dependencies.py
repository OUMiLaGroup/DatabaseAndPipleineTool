import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "configure_replay_dependencies",
    ROOT / "open_pilot_download_worker/scripts/configure_replay_dependencies.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ReplayDependenciesTests(unittest.TestCase):
    def test_preserves_frozen_install_and_surrounding_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "install.sh"
            script.write_text("#!/bin/bash\nuv sync --frozen --all-extras\nsource .venv/bin/activate\n")
            module.configure(script)
            expected = "#!/bin/bash\nuv sync --frozen --all-extras --no-extra tools\nsource .venv/bin/activate\n"
            self.assertEqual(script.read_text(), expected)
            module.configure(script)
            self.assertEqual(script.read_text(), expected)

    def test_unknown_installer_is_not_modified(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "install.sh"
            original = "uv sync --all-extras\n"
            script.write_text(original)
            with self.assertRaises(ValueError):
                module.configure(script)
            self.assertEqual(script.read_text(), original)


if __name__ == "__main__":
    unittest.main()
