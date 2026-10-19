#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute actual controller functions with mocked Android operations."""
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'module/control.sh').read_text()
def function(name):
    match = re.search(r'^' + name + r'\(\) \{\n.*?^\}\n', source, re.M | re.S)
    assert match, name
    return match.group()
functions = function('record_watcher_exit') + function('activate')

def run(signal='', enabled=True, fault=False, marker='', activate=False):
    with tempfile.TemporaryDirectory() as d:
        state = Path(d)
        (state/'run').mkdir()
        if enabled: (state/'ENABLE').touch()
        if fault: (state/'FAULT').write_text('existing')
        if marker: (state/'run/watch.stopped.boot').write_text(marker+'\n')
        script = f'''STATE='{d}'
RUN="$STATE/run"
BOOT=current-boot
WATCH_SIGNAL={signal}
set_off() {{ echo 0 > "$STATE/flag"; }}
fault() {{ rm -f "$STATE/ENABLE"; echo "$*" > "$STATE/FAULT"; return 1; }}
note() {{ echo "$*" >> "$STATE/events"; }}
verify_activation() {{ exit 42; }}
'''+functions+'\nrecord_watcher_exit\n'
        if activate: script+='activate\n'
        result = subprocess.run(['/bin/sh'], input=script, text=True, capture_output=True)
        return result.returncode, {str(p.relative_to(state)):p.read_text() for p in state.rglob('*') if p.is_file()}

cases=[]
for signal in ('TERM','INT','HUP'):
    code, files = run(signal, activate=True)
    assert code == 75 and files['flag']=='0\n' and 'ENABLE' in files and 'FAULT' not in files
    assert files['run/watch.stopped.boot']=='current-boot\n'
    cases.append(signal+': OFF, preserve intent, reject same-boot activation')
_, files=run('TERM', enabled=False)
assert 'run/watch.stopped.boot' not in files and 'FAULT' not in files
cases.append('explicit pause creates no stop marker')
_, files=run('TERM', fault=True)
assert files['FAULT']=='existing' and 'run/watch.stopped.boot' not in files
cases.append('existing integrity fault remains unchanged')
_, files=run()
assert 'FAULT' in files and 'ENABLE' not in files
cases.append('unsignalled exit remains persistent fault')
code, files=run(enabled=False, marker='previous-boot', activate=True)
assert code==42 and files['flag']=='0\n'
cases.append('new boot reaches full activation validation, never directly arms')
result={'passed':len(cases),'cases':cases,'limits':'Mocked host control flow only; device reboot still required.'}

print(f'{len(cases)} watcher exit cases PASS')
