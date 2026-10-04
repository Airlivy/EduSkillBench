import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import REPO
from snapshot import source_inventory, content_id


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', '-m', 'repro', *args],
                              cwd=REPO, text=True, capture_output=True, timeout=15)

    def test_help_and_unknown_command(self):
        self.assertEqual(self.run_cli('--help').returncode, 0)
        self.assertEqual(self.run_cli('not-a-command').returncode, 2)

    def test_dispatch_preserves_incomplete_status_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli('check', '--jobs-dir', tmp, '--all')
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('INCOMPLETE', result.stdout)
        result = self.run_cli('run', '--tag', 'cli-offline-test', '--models', 'glm-5.3',
                              '--task-id', 'lesson-builder__01')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Dry-run only', result.stdout)
        self.assertFalse((REPO/'jobs/protocols/cli-offline-test').exists())

    def test_snapshot_identity_tracks_content_not_runtime_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'repro').mkdir(); (root/'jobs').mkdir()
            source = root/'repro/example.py'; source.write_text('x = 1\n')
            first = content_id(source_inventory(root))
            (root/'jobs/example.json').write_text('{}')
            self.assertEqual(content_id(source_inventory(root)), first)
            source.write_text('x = 2\n')
            self.assertNotEqual(content_id(source_inventory(root)), first)


if __name__ == '__main__':
    unittest.main()
