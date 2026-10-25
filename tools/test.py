#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run portable regression checks; no phone or ROM binaries are required."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
cc = os.environ.get('HOST_CC', os.environ.get('CC', 'clang'))
with tempfile.TemporaryDirectory() as name:
    # One native build per telephoto camera ID in profile.json: 3 (15T), 4 (OnePlus 15).
    for tele in (3, 4):
        for test in ('guard', 'provider'):
            binary = Path(name)/f'{test}{tele}'
            subprocess.run([cc, '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                            '-ffp-contract=off', '-fno-omit-frame-pointer', '-fsanitize=address,undefined',
                            f'-DZOOM_FIX_TELE_ID={tele}', '-pthread', str(ROOT/f'tests/{test}_test.c'),
                            '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
for test in ('controller', 'checkpoint', 'installer', 'manager', 'allowlist', 'conventions'):
    subprocess.run([sys.executable, str(ROOT/f'tests/{test}_test.py')], check=True)
for path in (ROOT/'module').glob('*.sh'):
    subprocess.run(['/bin/sh', '-n', str(path)], check=True)
print('All host checks passed.')
