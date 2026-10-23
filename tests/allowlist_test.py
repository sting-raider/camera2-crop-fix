#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the exact LineageOS build allowlist in the installer and controller."""
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build', ROOT/'tools/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
PROFILE = json.loads((ROOT/'profile.json').read_text())


def function(path, name):
    match = re.search(r'^' + name + r'\(\) \{\n.*?^\}\n', (ROOT/path).read_text(), re.M | re.S)
    assert match, (path, name)
    return match.group()


class AllowlistTests(unittest.TestCase):
    def supported(self, script, running, versions=None):
        # Same quoting as the profile.sh that tools/build.py generates.
        listed = shlex.quote(' '.join(PROFILE['lineage_versions'] if versions is None else versions))
        program = f'''LINEAGE_VERSIONS={listed}
getprop() {{ [ "$1" = ro.lineage.version ] && printf '%s\\n' {shlex.quote(running)}; }}
{function(script, 'lineage_supported')}lineage_supported
'''
        return subprocess.run(['/bin/sh'], input=program, text=True, capture_output=True).returncode == 0

    def test_scripts_share_one_check(self):
        self.assertEqual(function('module/control.sh', 'lineage_supported'),
                         function('module/customize.sh', 'lineage_supported'))

    def test_profile_lists_required_builds(self):
        self.assertEqual(build.lineage_versions(PROFILE), [
            f'24.0-{date}-NIGHTLY-fairlady' for date in ('20261011', '20261014', '20261015', '20261022')])

    def test_exact_matches_only(self):
        for script in ('module/control.sh', 'module/customize.sh'):
            for version in PROFILE['lineage_versions']:
                self.assertTrue(self.supported(script, version), (script, version))
            for version in ('', '*', '24.0-20261013-NIGHTLY-fairlady', '24.0-20261022-NIGHTLY-fairlad',
                            '24.0-20261022-NIGHTLY-fairlady ', '24.0-20261022', 'fairlady',
                            ' '.join(PROFILE['lineage_versions'][:2])):
                self.assertFalse(self.supported(script, version), (script, repr(version)))

    def test_build_rejects_bad_allowlists(self):
        for versions in ([], '24.0-20261011-NIGHTLY-fairlady', ['24.0-20261011-NIGHTLY-fairlady'] * 2,
                         ['24.0-2026101-NIGHTLY-fairlady'], ['24.0-20261011-NIGHTLY-fairlady x'], [11]):
            with self.assertRaises(ValueError, msg=repr(versions)):
                build.lineage_versions({'lineage_versions': versions})
        for profile in ({}, {'lineage_version': '24.0-20261011-NIGHTLY-fairlady'},
                        {'lineage_version': 'x', 'lineage_versions': ['24.0-20261011-NIGHTLY-fairlady']}):
            with self.assertRaises(ValueError, msg=repr(profile)):
                build.lineage_versions(profile)

    def test_gates_use_check(self):
        self.assertIn('  lineage_supported &&\n', function('module/control.sh', 'verify_activation'))
        self.assertIn('\nlineage_supported &&\n', (ROOT/'module/customize.sh').read_text())
        for path in ('module/control.sh', 'module/customize.sh'):
            self.assertNotRegex((ROOT/path).read_text(), r'\$\{?LINEAGE_VERSION\b')


if __name__ == '__main__':
    unittest.main()
