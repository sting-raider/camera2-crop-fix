#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression checks for titles, proposed commit ranges and invalid headers."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('conventions', ROOT/'tools/check_conventions.py')
conventions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conventions)


class ConventionsTests(unittest.TestCase):
    def test_headers(self):
        for title in ('fix(native): preserve crop geometry', 'feat(module)!: change the interface',
                      'docs(readme): document OnePlus support'):
            self.assertTrue(conventions.valid_header(title, pr=True), title)
        self.assertTrue(conventions.valid_header('test: x'))
        for title in ('fix: missing PR scope', 'Update README', '[fix][native] zoom',
                      'fix(Native): uppercase scope', 'fix(native): ', 'fix(native): trailing ',
                      'fix(native): line\nbreak', 'fix(native): tab\there', 'fix(native): '+'x'*100):
            self.assertFalse(conventions.valid_header(title, pr=True), repr(title))

    def test_proposed_range(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            def git(*args):
                return subprocess.check_output(['git', '-C', name, *args], text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            # Existing repository history is deliberately outside the PR range.
            git('-c', 'core.hooksPath=/dev/null', 'commit', '-q', '--allow-empty', '-m', 'Initial commit')
            base = git('rev-parse', 'HEAD')
            git('-c', 'core.hooksPath=/dev/null', 'commit', '-q', '--allow-empty', '-m', 'feat: add module')
            event = {'pull_request': {'title': 'feat(module): add crop correction',
                     'base': {'sha': base}, 'head': {'sha': git('rev-parse', 'HEAD')}}}
            path = directory/'event.json'
            def run():
                path.write_text(json.dumps(event))
                return subprocess.run(['python3', str(ROOT/'tools/check_conventions.py'), str(path)],
                                      cwd=name, capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            git('-c', 'core.hooksPath=/dev/null', 'commit', '-q', '--allow-empty', '-m', 'bad message')
            event['pull_request']['head']['sha'] = git('rev-parse', 'HEAD')
            self.assertNotEqual(run().returncode, 0)
            event['pull_request']['title'] = 'invalid title'
            self.assertIn('PR title must use', run().stderr)


if __name__ == '__main__':
    unittest.main()
