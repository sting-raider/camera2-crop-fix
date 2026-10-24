#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the exact per-device LineageOS build allowlist in the installer and controller."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build', ROOT/'tools/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
PROFILE = json.loads((ROOT/'profile.json').read_text())
FAIRLADY = 'OnePlus/PLZ110/OP64DDL1:16/BP2A.250605.015/B.40e10d0-1bdc90a-1c00f52:user/release-keys'
INFINITI = 'OnePlus/CPH2745IN/OP611FL1:16/BP2A.250605.015/B.R4T3.1abf132_aeee51_aea830:user/release-keys'


def function(path, name):
    match = re.search(r'^(?:#[^\n]*\n)?' + name + r'\(\) \{\n.*?^\}\n', (ROOT/path).read_text(), re.M | re.S)
    assert match, (path, name)
    return match.group()


class AllowlistTests(unittest.TestCase):
    def supported(self, script, version, fingerprint):
        """Return the matched codename, or None when the gate rejects the running build."""
        with tempfile.NamedTemporaryFile('w') as builds:
            builds.write(build.build_list(build.devices(PROFILE)))
            builds.flush()
            program = f'''getprop() {{
  case "$1" in
    ro.lineage.version) printf '%s\\n' {shlex.quote(version)};;
    ro.vendor.build.fingerprint) printf '%s\\n' {shlex.quote(fingerprint)};;
  esac
}}
{function(script, 'build_supported')}build_supported {shlex.quote(builds.name)} && printf '%s' "$CODENAME"
'''
            result = subprocess.run(['/bin/sh'], input=program, text=True, capture_output=True)
            return result.stdout if result.returncode == 0 else None

    def test_scripts_share_one_check(self):
        self.assertEqual(function('module/control.sh', 'build_supported'),
                         function('module/customize.sh', 'build_supported'))

    def test_profile_lists_required_builds(self):
        listed = {device['codename']: (device['lineage_versions'], device['vendor_fingerprint'])
                  for device in build.devices(PROFILE)}
        self.assertEqual(listed, {
            'fairlady': ([f'24.0-{date}-NIGHTLY-fairlady' for date in ('20261011', '20261014', '20261015', '20261022')],
                         FAIRLADY),
            'infiniti': ([f'24.0-{date}-NIGHTLY-infiniti' for date in ('20261014', '20261021')], INFINITI)})

    def test_exact_matches_only(self):
        for script in ('module/control.sh', 'module/customize.sh'):
            for device in build.devices(PROFILE):
                for version in device['lineage_versions']:
                    self.assertEqual(self.supported(script, version, device['vendor_fingerprint']),
                                     device['codename'], (script, version))
            for version, fingerprint in (
                    ('24.0-20261022-NIGHTLY-fairlady', INFINITI), ('24.0-20261021-NIGHTLY-infiniti', FAIRLADY),
                    ('24.0-20261022-NIGHTLY-fairlady', ''), ('', FAIRLADY), ('', ''), ('*', '*'),
                    ('24.0-20261021-NIGHTLY-fairlady', FAIRLADY), ('24.0-20261022-NIGHTLY-infiniti', INFINITI),
                    ('24.0-20261022-NIGHTLY-fairlad', FAIRLADY), ('24.0-20261022-NIGHTLY-fairlady ', FAIRLADY),
                    ('24.0-20261022-NIGHTLY-fairlady', FAIRLADY + ' fairlady'), ('24.0-20261022', FAIRLADY),
                    ('24.0-20261011-NIGHTLY-fairlady 24.0-20261014-NIGHTLY-fairlady', FAIRLADY)):
                self.assertIsNone(self.supported(script, version, fingerprint), (script, version, fingerprint))

    def test_dependency_lists(self):
        lists = build.dependency_lists(PROFILE, build.devices(PROFILE))
        self.assertEqual(sorted(lists), ['fairlady', 'infiniti'])
        for device in build.devices(PROFILE):
            lines = lists[device['codename']].splitlines()
            expected = {**PROFILE['dependencies'], **device['dependencies']}
            self.assertEqual(lines, [f'{digest}  {path}' for path, digest in expected.items()])
            self.assertEqual(len(lines), 3)

    def test_build_rejects_bad_profiles(self):
        def changed(edit):
            profile = copy.deepcopy(PROFILE)
            edit(profile)
            return profile
        bad = [
            changed(lambda p: p.update(lineage_versions=['24.0-20261011-NIGHTLY-fairlady'])),
            changed(lambda p: p.update(vendor_fingerprint=FAIRLADY)),
            changed(lambda p: p.update(devices=[])),
            changed(lambda p: p.pop('devices')),
            changed(lambda p: p['devices'][0].update(lineage_versions=[])),
            changed(lambda p: p['devices'][0].update(lineage_versions='24.0-20261011-NIGHTLY-fairlady')),
            changed(lambda p: p['devices'][0].update(lineage_versions=['24.0-20261011-NIGHTLY-infiniti'])),
            changed(lambda p: p['devices'][0].update(lineage_versions=['24.0-2026101-NIGHTLY-fairlady'])),
            changed(lambda p: p['devices'][0].update(lineage_versions=['24.0-20261011-NIGHTLY-fairlady x'])),
            changed(lambda p: p['devices'][0]['lineage_versions'].append('24.0-20261011-NIGHTLY-fairlady')),
            changed(lambda p: p.update(lineage_version='24.0-20261011-NIGHTLY-fairlady')),
            changed(lambda p: p['devices'].append({**copy.deepcopy(p['devices'][1]),
                                                   'lineage_versions': ['24.0-20261028-NIGHTLY-infiniti']})),
            changed(lambda p: p['devices'][1].update(codename='fairlady')),
            changed(lambda p: p['devices'][1].update(codename='../x')),
            changed(lambda p: p['devices'][0].update(vendor_fingerprint=FAIRLADY + ' x')),
            changed(lambda p: p['devices'][0].update(vendor_fingerprint='')),
            changed(lambda p: p['devices'][0].pop('name')),
            changed(lambda p: p['devices'][0].update(extra=1)),
            changed(lambda p: p['devices'][0]['dependencies'].update(PROFILE['dependencies'])),
            changed(lambda p: p['devices'][0]['dependencies'].update({'/vendor/lib64/x.so': 'A' * 64})),
            changed(lambda p: p['dependencies'].update({'relative.so': '0' * 64})),
        ]
        for profile in bad:
            with self.assertRaises(ValueError):
                build.devices(profile)

    def test_gates_use_check(self):
        control, installer = (ROOT/'module/control.sh').read_text(), (ROOT/'module/customize.sh').read_text()
        self.assertIn('''
  build_supported "$MODDIR/builds" &&
    [ "$(getprop ro.build.display.id)" = "$DISPLAY_ID" ] || return 1
  sha256sum -c "$MODDIR/dependencies.$CODENAME.sha256" >> "$RUN/events.log" 2>&1 || return 1
''', function('module/control.sh', 'verify_activation'))
        self.assertIn('''
build_supported "$MODPATH/builds" &&
  [ "$(getprop ro.build.display.id)" = "$DISPLAY_ID" ] || abort "Unsupported ROM build"
sha256sum -c "$MODPATH/dependencies.$CODENAME.sha256" >/dev/null || abort "Unsupported camera libraries"
''', installer)
        for text in (control, installer):
            self.assertNotRegex(text, r'LINEAGE_VERSION|VENDOR_FINGERPRINT|dependencies\.sha256|lineage_supported')


if __name__ == '__main__':
    unittest.main()
