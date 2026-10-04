"""Exercise the image-lag workflow's scope decision against local Git history."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / '.github/workflows/ci-images-spacesd-lag.yml'


def git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


class LagScopeTests(unittest.TestCase):
    def run_scope(self, before: str | None, after: str, *, invalid_base: bool = False):
        # Run the shipped shell block; no substitute implementation or registry.
        workflow = WORKFLOW.read_text()
        scope = workflow.split('      - name: Does this PR release cua-spacesd itself?\n', 1)[1]
        script = textwrap.dedent(scope.split('        run: |\n', 1)[1].split('      - name:', 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            origin = Path(directory) / 'origin'
            repo = Path(directory) / 'checkout'
            origin.mkdir()
            git(origin, 'init', '-q')
            (origin / 'README.md').write_text('synthetic fixture\n')
            version = origin / 'libs/cua-spacesd/VERSION'
            if before is not None:
                version.parent.mkdir(parents=True)
                version.write_text(before + '\n')
            git(origin, 'add', '.')
            git(origin, '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                'commit', '-qm', 'base')
            base = git(origin, 'rev-parse', 'HEAD')
            git(origin, 'clone', '-q', str(origin), str(repo))
            version = repo / 'libs/cua-spacesd/VERSION'
            version.parent.mkdir(parents=True, exist_ok=True)
            version.write_text(after + '\n')
            output = Path(directory) / 'output'
            output.touch()
            result = subprocess.run(
                ['bash', '-c', script], cwd=repo, capture_output=True, text=True,
                env={**os.environ, 'BASE_SHA': '0' * 40 if invalid_base else base,
                     'GITHUB_OUTPUT': str(output)},
            )
            return result, output.read_text()

    def test_version_introduced_after_base_skips_catalog_lag(self):
        result, output = self.run_scope(None, '0.5.3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, 'skip=true\n')
        self.assertIn('(not present) -> 0.5.3', result.stdout)

    def test_existing_version_keeps_changed_and_unchanged_routes(self):
        for before, expected in [('0.5.2', 'skip=true\n'), ('0.5.3', '')]:
            with self.subTest(before=before):
                result, output = self.run_scope(before, '0.5.3')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output, expected)

    def test_invalid_base_is_not_treated_as_missing_version(self):
        result, output = self.run_scope(None, '0.5.3', invalid_base=True)
        self.assertEqual(result.returncode, 128, result.stderr)
        self.assertIn('not our ref', result.stderr)
        self.assertEqual(output, '')


if __name__ == '__main__':
    unittest.main()
