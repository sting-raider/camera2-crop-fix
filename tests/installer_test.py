#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual shell patch installer with disposable image fixtures."""
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def run_patch(self, corrupt_original=False, truncate=False, bad_target=False, short_plan=False,
                  codename='infiniti'):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            original = bytes(range(256)) * 4
            checksum = hashlib.sha256(original).hexdigest()
            data = bytearray(original)
            if corrupt_original:
                data[0] ^= 1
            (directory/'original').write_bytes(data)
            payload = b'ABCDabcdefgh12345678'
            (directory/'patch.infiniti.bin').write_bytes(payload[:-1] if truncate else payload)
            # Another device's payload of the same size must never be selected.
            (directory/'patch.fairlady.bin').write_bytes(b'Z' * len(payload))
            plan = ['0 16 4', '4 32 4', '8 48 4', '12 64 8']
            if bad_target:
                plan[-1] = '12 1020 8'
            if short_plan:
                plan.pop()
            (directory/'patch.plan').write_text('\n'.join(plan)+'\n')
            script = f'''MODPATH={shlex.quote(name)}
CODENAME={shlex.quote(codename)}
ORIGINAL={checksum}
ORIGINAL_SIZE={len(original)}
PATCH_SIZE={len(payload)}
. {shlex.quote(str(ROOT/'module/patch.sh'))}
patch_image "$MODPATH/original" "$MODPATH/patched"
'''
            result = subprocess.run(['/bin/sh'], input=script, text=True, capture_output=True)
            output = directory/'patched'
            return result.returncode, output.read_bytes() if output.exists() else None, original

    def test_exact_patch(self):
        code, actual, original = self.run_patch()
        expected = bytearray(original)
        for offset, data in ((16,b'ABCD'),(32,b'abcd'),(48,b'efgh'),(64,b'12345678')):
            expected[offset:offset+len(data)] = data
        self.assertEqual(code, 0)
        self.assertEqual(actual, bytes(expected))

    def test_wrong_original(self):
        self.assertNotEqual(self.run_patch(corrupt_original=True)[0], 0)

    def test_truncated_patch(self):
        self.assertNotEqual(self.run_patch(truncate=True)[0], 0)

    def test_target_bounds(self):
        self.assertNotEqual(self.run_patch(bad_target=True)[0], 0)

    def test_missing_region(self):
        self.assertNotEqual(self.run_patch(short_plan=True)[0], 0)

    def test_device_payload_selection(self):
        code, actual, original = self.run_patch(codename='fairlady')
        self.assertEqual(code, 0)
        self.assertEqual(actual[16:20], b'ZZZZ')
        self.assertEqual(actual[:16], original[:16])
        for codename in ('', 'missing', '../patch', 'infiniti/x', 'Infiniti', 'infiniti '):
            code, actual, _ = self.run_patch(codename=codename)
            self.assertNotEqual(code, 0, repr(codename))
            self.assertIsNone(actual, repr(codename))


if __name__ == '__main__':
    unittest.main()
