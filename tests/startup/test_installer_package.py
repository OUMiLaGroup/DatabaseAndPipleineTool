"""Exercise the actual compiled distributable without installing services."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PackageTests(unittest.TestCase):
    def run_installer(self, target):
        return subprocess.run([str(ROOT / 'MiLa-Installer.exe'), '--extract-only', str(target)], check=False).returncode

    def test_distribution_and_repeat_preserve_user_files(self):
        with tempfile.TemporaryDirectory(prefix='mila-release-test-') as temporary:
            target = Path(temporary) / 'project'
            self.assertEqual(self.run_installer(target), 0)
            manifest = json.loads((target / '.mila-release-manifest.json').read_text())
            for needed in ['launcher/Setup-MiLa.ps1', 'launcher/Ensure-Python.ps1', 'launcher/workspace.py', 'frontend/package.json', 'docker-compose.yaml', 'scripts/Start-MiLa.ps1', 'shared/depth_estimation.py', 'shared/depth_config.py', 'launcher/monocular-depth.json', 'docker-compose.gpu.yml', 'cvat_worker/requirements-depth.txt']:
                self.assertTrue((target / needed).is_file(), needed)
            for name in manifest:
                parts = Path(name).parts
                self.assertNotIn('.env', parts)
                self.assertNotIn('node_modules', parts)
                self.assertNotIn('postgres_data', parts)
                self.assertFalse(name.endswith('.license'))
                self.assertNotEqual(parts[0], 'cvat')
            (target / '.env').write_text('private account fixture')
            license = target / 'minio/minio.license'
            license.write_text('private license fixture')
            self.assertEqual(self.run_installer(target), 0)
            self.assertEqual((target / '.env').read_text(), 'private account fixture')
            self.assertEqual(license.read_text(), 'private license fixture')
            source = target / 'launcher/workspace.py'
            source.write_text('locally edited source')
            self.assertEqual(self.run_installer(target), 1)
            self.assertEqual(source.read_text(), 'locally edited source')

    def test_unmanaged_folder_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix='mila-release-test-') as temporary:
            target = Path(temporary)
            source = target / 'keep.txt'
            source.write_text('existing user file')
            self.assertEqual(self.run_installer(target), 1)
            self.assertEqual(list(target.iterdir()), [source])


if __name__ == '__main__':
    unittest.main()
