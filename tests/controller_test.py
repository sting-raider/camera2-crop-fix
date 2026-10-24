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

def restore(service_state, original=True):
    with tempfile.TemporaryDirectory() as d:
        script = f'''STATE='{d}'
RUN="$STATE/run"
mkdir "$RUN"
ORIGINAL=original
TARGET=/system/bin/cameraserver
log() {{ echo "$*" >> "$STATE/calls"; }}
pause() {{ log pause; }}
set_off() {{ log set_off; }}
fault() {{ log "fault $*"; return 1; }}
note() {{ :; }}
sleep() {{ :; }}
mount_id() {{ :; }}
pidof() {{ [ ! -e "$STATE/started" ] || echo 100; }}
one_pid() {{ [ -e "$STATE/started" ] && PID=100; }}
sha() {{ echo {'original' if original else 'other'}; }}
getprop() {{ if [ -e "$STATE/started" ]; then echo running; else echo '{service_state}'; fi; }}
setprop() {{ log "setprop $*"; [ "$1" != ctl.start ] || touch "$STATE/started"; }}
'''+function('restore').replace('/system/bin/setprop', 'setprop')+'restore\n'
        result = subprocess.run(['/bin/sh'], input=script, text=True, capture_output=True)
        calls = (Path(d)/'calls').read_text().splitlines()
        return result.returncode, calls
code, calls=restore('')
assert code==0 and calls==['pause', 'set_off'], calls
cases.append('restore before init starts cameraserver: no stop/start, no fault')
code, calls=restore('stopped')
assert code==0 and calls==['pause', 'setprop ctl.stop cameraserver', 'setprop ctl.start cameraserver', 'set_off'], calls
cases.append('restore with a stopped service still stops and starts it once')
for state in ('restarting', 'running'):
    code, calls=restore(state)
    assert code==1 and calls==['pause', 'fault absent camera PID requires verified original and stopped or unstarted init state'], calls
cases.append('restore with no PID mid-respawn remains a fault')
code, calls=restore('', original=False)
assert code==1 and not [c for c in calls if c.startswith('setprop')], calls
cases.append('restore before start still requires the verified original')
result={'passed':len(cases),'cases':cases,'limits':'Mocked host control flow only; device reboot still required.'}

print(f'{len(cases)} controller cases PASS')
