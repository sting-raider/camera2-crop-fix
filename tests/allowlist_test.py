#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the OnePlus 15-only profile: no ROM checks, only the cameraserver hash."""
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
    match = re.search(r'^(?:#[^\n]*\n)*' + name + r'\(\) \{(?: [^\n]*\}\n|\n.*?^\}\n)', (ROOT/path).read_text(), re.M | re.S)
    assert match, (path, name)
    return match.group()


class AllowlistTests(unittest.TestCase):
    def supported(self, script, version, fingerprint):
        program = f'''getprop() {{
  case "$1" in
    ro.lineage.version) printf '%s\\n' {shlex.quote(version)};;
    ro.vendor.build.fingerprint) printf '%s\\n' {shlex.quote(fingerprint)};;
  esac
}}
{function(script, 'build_supported')}build_supported /nonexistent && printf '%s %s' "$CODENAME" "$TELE_ID"
'''
        result = subprocess.run(['/bin/sh'], input=program, text=True, capture_output=True)
        return result.stdout if result.returncode == 0 else None

    def test_scripts_share_one_check(self):
        self.assertEqual(function('module/control.sh', 'build_supported'),
                         function('module/customize.sh', 'build_supported'))

    def test_profile_is_oneplus15_only(self):
        self.assertEqual([(d['codename'], d['telephoto_camera_id']) for d in build.devices(PROFILE)], [('infiniti', 4)])

    def test_any_rom_selects_oneplus15(self):
        for script in ('module/control.sh', 'module/customize.sh'):
            for version, fingerprint in (('24.0-20261014-NIGHTLY-infiniti', 'x'), ('24.0-20991231-NIGHTLY-fairlady', ''),
                                         ('', ''), ('25.0-UNOFFICIAL', 'other/fingerprint')):
                self.assertEqual(self.supported(script, version, fingerprint), 'infiniti 4', (script, version))

    def test_only_cameraserver_hash_gates(self):
        control, installer = (ROOT/'module/control.sh').read_text(), (ROOT/'module/customize.sh').read_text()
        for text in (control, installer):
            self.assertNotRegex(text, r'dependencies\.|ro\.lineage\.version|ro\.vendor\.build\.fingerprint|'
                                      r'ro\.build\.display\.id|LINEAGE_VERSION|VENDOR_FINGERPRINT')
        # The patch writes fixed offsets, so the original cameraserver must still match exactly.
        self.assertIn('= "$ORIGINAL" ]', installer)
        self.assertIn('build_supported "$MODDIR/builds" || return 1\n', function('module/control.sh', 'verify_activation'))
        self.assertIn('''changed_id2=%s changed_id%s=%s fault=0\\n' "$PID" "$VERIFIED" "$COUNT2" "$TELE_ID" "$COUNT_TELE"''',
                      function('module/control.sh', 'watch'))
        patcher = (ROOT/'module/patch.sh').read_text()
        self.assertIn('payload="$MODPATH/patch.$CODENAME.bin"', patcher)


if __name__ == '__main__':
    unittest.main()
