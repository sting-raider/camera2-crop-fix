#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the actual entry scripts and controller prologue against fake root-manager tools."""
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODID = 'camera2_native_zoom_fix'
KEY = 'persist.camera.zoom_crop_fix'
CONTROL = f'/data/adb/modules/{MODID}/control.sh'
MAGISK = {
    'service.sh': f'magisk/magisk su -mm -c exec /data/adb/magisk/busybox sh {CONTROL} boot',
    'action.sh': f'magisk/magisk su -mm -c /data/adb/magisk/busybox sh {CONTROL} toggle; action_result=$?; '
                 f'/data/adb/magisk/busybox sh {CONTROL} status; exit "$action_result"',
    'uninstall.sh': f'magisk/magisk su -mm -c /data/adb/magisk/busybox sh {CONTROL} restore',
}
APATCH = {'APATCH': 'true', 'APATCH_VER_CODE': '11282', 'ASH_STANDALONE': '1'}


class Device:
    """A temporary /data/adb holding fake Magisk and/or APatch tools that log their calls."""

    def __init__(self, directory, magisk, ap):
        self.root = Path(os.path.realpath(directory))
        self.adb = self.root/'data/adb'
        self.bin = self.root/'bin'
        self.log = self.root/'log'
        self.boot_id = self.root/'boot_id'
        self.boot_id.write_text('current-boot\n')
        self.mod = self.adb/'modules'/MODID
        self.mod.mkdir(parents=True)
        for script in ('action.sh', 'service.sh', 'uninstall.sh'):
            (self.mod/script).write_text(self.local((ROOT/'module'/script).read_text()))
        (self.mod/'control.sh').write_text(f'echo "control $*" >> {self.log}\n'
                                           '[ "$1" = status ] && exit 0\nexit "${CONTROL_EXIT:-0}"\n')
        self.exe(self.bin/'id', 'echo 0', log=False)
        self.exe(self.bin/'getprop', 'echo 0', log=False)
        if magisk:
            self.exe(self.adb/'magisk/magisk', 'if [ "$1" = su ] && [ "$2" = -mm ] && [ "$3" = -c ]; then exec /bin/sh -c "$4"; fi')
            self.exe(self.adb/'magisk/busybox', '[ "$1" = sh ] && shift && exec /bin/sh "$@"')
        if ap:
            self.exe(self.adb/'ap/bin/busybox', '[ "$1" = sh ] && shift && exec /bin/sh "$@"')
            self.exe(self.adb/'ap/bin/resetprop', ':')

    def local(self, text):
        return (text.replace('/data/adb/', f'{self.adb}/')
                    .replace('/proc/sys/kernel/random/boot_id', str(self.boot_id)))

    def exe(self, path, body, log=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        record = f'echo "{path.relative_to(self.adb)} $*" >> {self.log}\n' if log else ''
        path.write_text(f'#!/bin/sh\n{record}{body}\n')
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def run(self, command, env=None, script=None):
        self.log.write_text('')
        result = subprocess.run(['/bin/sh', *command], input=script, capture_output=True, text=True,
                                env={'PATH': f'{self.bin}:/usr/bin:/bin', **(env or {})})
        calls = self.log.read_text().replace(str(self.adb), '/data/adb').splitlines()
        return result.returncode, calls, result.stdout

    def entry(self, script, *args, env=None):
        return self.run([str(self.mod/script), *args], env)


class EntryScriptTests(unittest.TestCase):
    def test_magisk_commands_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            device = Device(d, magisk=True, ap=False)
            for script, command in MAGISK.items():
                self.assertEqual(device.entry(script)[1][0], command, script)
            self.assertEqual(device.entry('service.sh', 'watch')[1][0], f'magisk/busybox sh {CONTROL} watch')

    def test_leftover_apatch_files_do_not_change_magisk(self):
        with tempfile.TemporaryDirectory() as d:
            device = Device(d, magisk=True, ap=True)
            for script, command in MAGISK.items():
                self.assertEqual(device.entry(script)[1][0], command, script)

    def test_apatch_uses_own_tools(self):
        for magisk in (False, True):
            with tempfile.TemporaryDirectory() as d:
                device = Device(d, magisk=magisk, ap=True)
                for script, args, mode in (('service.sh', (), 'boot'), ('service.sh', ('watch',), 'watch'),
                                           ('uninstall.sh', (), 'restore'), ('action.sh', (), 'toggle')):
                    calls = device.entry(script, *args, env=APATCH)[1]
                    self.assertEqual(calls[0], f'ap/bin/busybox sh {CONTROL} {mode}', (script, magisk))
                    self.assertFalse([call for call in calls if call.startswith('magisk/')], (script, magisk))

    def test_action_exit_status_and_status_report(self):
        for magisk, ap, env in ((True, False, {}), (False, True, APATCH)):
            with tempfile.TemporaryDirectory() as d:
                code, calls, _ = Device(d, magisk, ap).entry('action.sh', env={**env, 'CONTROL_EXIT': '75'})
                self.assertEqual(code, 75)
                self.assertEqual([call for call in calls if call.startswith('control')],
                                 ['control toggle', 'control status'])


class ControllerTests(unittest.TestCase):
    source = (ROOT/'module/control.sh').read_text()

    def test_tool_selection(self):
        prologue = self.source.split('if [ "${ASH_STANDALONE:-0}" != 1 ]; then')[0]
        set_off = re.search(r'^set_off\(\) \{.*\}$', self.source, re.M).group()
        for magisk, ap, env, tool, exported in (
                (True, False, {}, 'magisk/magisk resetprop', ''),
                (True, True, {}, 'magisk/magisk resetprop', ''),
                (False, True, {}, 'ap/bin/resetprop', 'true'),
                (False, True, APATCH, 'ap/bin/resetprop', 'true'),
                (True, True, APATCH, 'ap/bin/resetprop', 'true')):
            with tempfile.TemporaryDirectory() as d:
                device = Device(d, magisk, ap)
                # The watcher is a child process, so only an exported value reaches it.
                script = device.local(prologue) + f'KEY={KEY}\n{set_off}\nset_off\n/bin/sh -c \'echo "APATCH=$APATCH"\'\n'
                _, calls, out = device.run([], env, script)
                self.assertEqual(calls, [f'{tool} -n {KEY} 0'], (magisk, ap, env))
                self.assertEqual(out.strip(), f'APATCH={exported}', (magisk, ap, env))

    def boot_entry(self, recorded, env, mode='boot', symlink=False):
        """Run control.sh up to its status branch; return resetprop calls and whether it got there."""
        with tempfile.TemporaryDirectory() as d:
            device = Device(d, magisk=True, ap=True)
            (device.mod/'profile.sh').write_text('')
            state = device.adb/'camera2_native_zoom_fix'
            if symlink:
                state.symlink_to(device.root/'elsewhere')
                state = device.root/'elsewhere'
            (state/'run').mkdir(parents=True)
            if recorded:
                (state/'run/boot.id').write_text(recorded + '\n')
            prologue = self.source.split('if [ "$MODE" = status ]; then')[0]
            (device.mod/'control.sh').write_text(device.local(prologue) + 'echo reached\n')
            _, calls, out = device.run([str(device.mod/'control.sh'), mode], {'ASH_STANDALONE': '1', **env})
            return calls, out.strip() == 'reached'

    def test_apatch_soft_reboot_keeps_state(self):
        self.assertEqual(self.boot_entry('current-boot', APATCH), ([], False))

    def test_new_boot_clears_flag(self):
        for recorded in ('previous-boot', ''):
            self.assertEqual(self.boot_entry(recorded, APATCH), ([f'ap/bin/resetprop -n {KEY} 0'], True))

    def test_magisk_same_boot_unchanged(self):
        self.assertEqual(self.boot_entry('current-boot', {}), ([f'magisk/magisk resetprop -n {KEY} 0'], True))

    def test_symlinked_state_never_skips_boot_reset(self):
        self.assertEqual(self.boot_entry('current-boot', APATCH, symlink=True),
                         ([f'ap/bin/resetprop -n {KEY} 0'], True))

    def test_missing_boot_id_never_skips_boot_reset(self):
        for boot_id in (None, ''):  # unreadable, or read as empty with no recorded boot
            with tempfile.TemporaryDirectory() as d:
                device = Device(d, magisk=False, ap=True)
                (device.mod/'profile.sh').write_text('')
                (device.adb/'camera2_native_zoom_fix/run').mkdir(parents=True)
                if boot_id is None:
                    device.boot_id.unlink()
                else:
                    device.boot_id.write_text(boot_id)
                prologue = self.source.split('if [ "$MODE" = status ]; then')[0]
                (device.mod/'control.sh').write_text(device.local(prologue) + 'echo reached\n')
                _, calls, out = device.run([str(device.mod/'control.sh'), 'boot'], {'ASH_STANDALONE': '1', **APATCH})
                self.assertEqual((calls, out.strip()), ([f'ap/bin/resetprop -n {KEY} 0'], 'reached'), repr(boot_id))

    def test_soft_reboot_check_is_boot_only(self):
        self.assertEqual(self.boot_entry('current-boot', APATCH, mode='on'), ([], True))


class InstallerGateTests(unittest.TestCase):
    def test_root_manager_gate(self):
        gate = (ROOT/'module/customize.sh').read_text().split('(cd "$MODPATH"')[0]
        for env, ap, message in (
                ({'APATCH': 'true', 'APATCH_VER_CODE': '11039', 'MAGISK_VER_CODE': '27000'}, True, None),
                ({'APATCH': 'true', 'APATCH_VER_CODE': '11282', 'MAGISK_VER_CODE': '30000'}, True, None),
                ({'APATCH': 'true', 'APATCH_VER_CODE': '10763', 'MAGISK_VER_CODE': '27000'}, True,
                 'APatch 11039 or newer is required'),
                ({'APATCH': 'true', 'MAGISK_VER_CODE': '30000'}, True, 'APatch 11039 or newer is required'),
                ({'APATCH': 'true', 'APATCH_VER_CODE': '11282'}, False, 'APatch busybox/resetprop not found'),
                ({'MAGISK_VER_CODE': '30700'}, False, None),
                ({'MAGISK_VER_CODE': '30600'}, False, 'Magisk 30.7 or newer is required'),
                ({'KSU': 'true', 'MAGISK_VER_CODE': '25200'}, True, 'Magisk 30.7 or newer is required')):
            with tempfile.TemporaryDirectory() as d:
                device = Device(d, magisk=False, ap=ap)
                script = 'abort() { echo "$*"; exit 9; }\nARCH=arm64\nBOOTMODE=true\n' + device.local(gate) + 'echo passed\n'
                self.assertEqual(device.run([], env, script)[2].strip(), message or 'passed', env)


if __name__ == '__main__':
    unittest.main()
