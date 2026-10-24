#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute checkpoint readiness, boot deferral and integrity checks from control.sh."""
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'module/control.sh').read_text()
PENDING = 'rw,seclabel,nodiscard,checkpoint=disable:5642540,checkpoint_merge'
COMMITTED = 'rw,seclabel,discard,discard_unit=block,checkpoint_merge'


def function(name):
    match = re.search(r'^' + name + r'\(\) \{[^\n]*\}\n|^' + name + r'\(\) \{\n.*?^\}\n',
                      SOURCE, re.M | re.S)
    assert match, name
    return (match.group().replace('/proc/self/mountinfo', '"$STATE/mountinfo"')
            .replace('/proc/uptime', '"$STATE/uptime"')
            .replace('/system/bin/vdc', 'vdc'))


def mountinfo(options=COMMITTED, target='ro,relatime', mount_id='142'):
    return (f'{mount_id} 45 254:50 / /data rw,nosuid,nodev,noatime shared:50 - '
            f'f2fs /dev/block/dm-50 {options}\n'
            f'300 45 254:50 /payload /system/bin/cameraserver {target} - '
            f'f2fs /dev/block/dm-50 {options}\n')


class CheckpointTests(unittest.TestCase):
    def run_shell(self, script, options=COMMITTED, enabled=True, existing_fault=False,
                  checkpoint_code=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'run').mkdir()
            (root/'module').mkdir()
            (root/'mountinfo').write_text(mountinfo(options))
            (root/'committed.mountinfo').write_text(mountinfo())
            (root/'checkpoint.code').write_text(str(checkpoint_code)+'\n')
            (root/'uptime').write_text('0.00 0.00\n')
            if enabled:
                (root/'ENABLE').touch()
            if existing_fault:
                (root/'FAULT').write_text('original fault\n')
            setup = f'''STATE={shlex.quote(directory)}
RUN="$STATE/run"
MODDIR="$STATE/module"
BOOT=current-boot
TARGET=/system/bin/cameraserver
APATCH=false
SLEEPS=0
log() {{ echo "$*" >> "$STATE/calls"; }}
set_off() {{ log off; echo 0 > "$STATE/flag"; }}
note() {{ log "note $*"; }}
tick() {{
  read -r now rest < "$STATE/uptime"
  printf '%s.00 0.00\\n' "$((${{now%%.*}}+$1))" > "$STATE/uptime"
}}
vdc() {{
  [ "$*" = 'checkpoint needsCheckpoint' ] || return 99
  echo query >> "$STATE/queries"
  return "$(cat "$STATE/checkpoint.code")"
}}
timeout() {{
  [ "$1" = 2 ] || return 99
  shift
  "$@"; query_result=$?
  [ "$query_result" != 124 ] || tick 2
  return "$query_result"
}}
flock() {{ log "lock $*"; }}
sleep() {{ SLEEPS=$((SLEEPS+1)); log sleep; tick "$1"; }}
'''
            functions = ''.join(function(name) for name in ('number', 'data_mount', 'data_ready',
                                                            'wait_for_data', 'fault'))
            result = subprocess.run(['/bin/sh'], input=setup+functions+script, text=True,
                                    capture_output=True, timeout=10)
            files = {str(path.relative_to(root)): path.read_text()
                     for path in root.rglob('*') if path.is_file()}
            return result.returncode, files, result.stdout, result.stderr

    def test_ready_without_checkpoint_property(self):
        code, _, _, _ = self.run_shell('data_ready\n')
        self.assertEqual(code, 0)

    def test_pending_query_error_and_timeout_never_report_ready(self):
        for checkpoint_code in (1, 25, 124):
            with self.subTest(checkpoint_code=checkpoint_code):
                code, files, _, _ = self.run_shell('data_ready\n', checkpoint_code=checkpoint_code)
                self.assertEqual(code, checkpoint_code)
                self.assertEqual(files['queries'], 'query\n')

    def boot_tail(self, prefix=''):
        return prefix+'''
MODE=boot
mount_id() { :; }
activate() { log activate; }
'''+SOURCE[SOURCE.index('[ "$MODE" != watch ]'):]

    def test_commit_finishes_before_boot_takes_locks_and_activates(self):
        script = self.boot_tail('''sleep() {
  SLEEPS=$((SLEEPS+1)); log sleep
  cp "$STATE/committed.mountinfo" "$STATE/mountinfo"
  echo 0 > "$STATE/checkpoint.code"
}
''')
        code, files, _, error = self.run_shell(script, options=PENDING, checkpoint_code=1)
        self.assertEqual(code, 0, error)
        calls = files['calls'].splitlines()
        self.assertEqual(calls[0], 'sleep')
        self.assertEqual(calls[-1], 'activate')
        self.assertTrue(all(call.startswith('lock ') for call in calls[1:-2]), calls)
        self.assertIn('ENABLE', files)
        self.assertNotIn('FAULT', files)

    def test_timeout_preserves_enable_without_locks_or_fault(self):
        # F2FS may already display committed options during remount; vold's
        # serialized query must still prevent activation until commit returns.
        code, files, _, _ = self.run_shell(self.boot_tail(), checkpoint_code=1)
        self.assertEqual(code, 75)
        self.assertEqual(files['calls'].splitlines(), ['sleep']*60)
        self.assertIn('ENABLE', files)
        self.assertNotIn('FAULT', files)
        self.assertIn('timed out', files['run/status'])
        self.assertNotIn('run/boot.id', files)

    def test_query_timeouts_count_toward_monotonic_wait_limit(self):
        code, files, _, _ = self.run_shell(self.boot_tail(), checkpoint_code=124)
        self.assertEqual(code, 75)
        self.assertLess(len(files['calls'].splitlines()), 60)
        self.assertIn('ENABLE', files)
        self.assertNotIn('FAULT', files)
        self.assertIn('timed out', files['run/status'])

    def test_pause_disable_remove_or_fault_cancels_unlocked_wait(self):
        for action in ('rm "$STATE/ENABLE"', 'touch "$MODDIR/disable"',
                       'touch "$MODDIR/remove"', 'echo reviewed > "$STATE/FAULT"'):
            with self.subTest(action=action):
                script = self.boot_tail('sleep() { log sleep; '+action+'; }\n')
                code, files, _, _ = self.run_shell(script, options=PENDING, checkpoint_code=1)
                self.assertEqual(code, 75)
                self.assertEqual(files['calls'].splitlines(), ['sleep'])
                self.assertNotIn('run/boot.id', files)
                if 'reviewed' in action:
                    self.assertEqual(files['FAULT'], 'reviewed\n')
                else:
                    self.assertNotIn('FAULT', files)

    def test_existing_fault_is_not_rewritten_while_waiting(self):
        code, files, _, _ = self.run_shell(self.boot_tail(), options=PENDING,
                                          existing_fault=True, checkpoint_code=1)
        self.assertEqual(code, 75)
        self.assertEqual(files['FAULT'], 'original fault\n')
        self.assertNotIn('calls', files)

    def test_apatch_second_boot_entry_preserves_an_activation_completed_during_wait(self):
        script = self.boot_tail('''APATCH=true
sleep() {
  log sleep
  cp "$STATE/committed.mountinfo" "$STATE/mountinfo"
  echo 0 > "$STATE/checkpoint.code"
  echo "$BOOT" > "$RUN/boot.id"
}
''')
        code, files, _, error = self.run_shell(script, options=PENDING, checkpoint_code=1)
        self.assertEqual(code, 0, error)
        self.assertNotIn('off', files['calls'].splitlines())
        self.assertNotIn('activate', files['calls'].splitlines())
        self.assertNotIn('FAULT', files)

    def test_manual_activation_rechecks_after_preflight_before_any_bind_or_intent(self):
        for enabled in (False, True):
            for checkpoint_code in (1, 25, 124):
                with self.subTest(enabled=enabled, checkpoint_code=checkpoint_code):
                    script = '''ORIGINAL=original
CANDIDATE=candidate
verify_activation() {
  log verify
  echo REJECT_CODE > "$STATE/checkpoint.code"
}
pidof() { :; }
'''.replace('REJECT_CODE', str(checkpoint_code))+function('activate')+'activate\n'
                    code, files, _, error = self.run_shell(script, enabled=enabled)
                    self.assertEqual(code, 75, error)
                    self.assertEqual(files['calls'].splitlines(), ['off', 'verify'])
                    self.assertEqual('ENABLE' in files, enabled)
                    self.assertNotIn('FAULT', files)
                    self.assertNotIn('run/boot.id', files)
                    self.assertNotIn('run/data.mount', files)

    def test_committed_parent_and_owned_target_still_require_exact_integrity(self):
        owned_flags = function('owned_flags')
        code, _, _, error = self.run_shell(owned_flags+'''
data_mount > "$RUN/data.mount"
owned_flags || exit 10
sed 's/discard,discard_unit=block/nodiscard/' "$STATE/mountinfo" > "$STATE/changed"
mv "$STATE/changed" "$STATE/mountinfo"
if owned_flags; then exit 11; fi
cp "$STATE/committed.mountinfo" "$STATE/mountinfo"
sed 's/ro,relatime/ro,noexec,relatime/' "$STATE/mountinfo" > "$STATE/changed"
mv "$STATE/changed" "$STATE/mountinfo"
if owned_flags; then exit 12; fi
''')
        self.assertEqual(code, 0, error)


if __name__ == '__main__':
    unittest.main()
