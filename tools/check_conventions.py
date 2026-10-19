#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check PR titles and every proposed commit without third-party packages."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

TYPES = r'(?:build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)'
SCOPE = r'\([a-z][a-z0-9-]*\)'


def valid_header(value, *, pr=False):
    scope = SCOPE if pr else f'(?:{SCOPE})?'
    return (len(value) <= 100 and all(ord(c) >= 32 and ord(c) != 127 for c in value)
            and re.fullmatch(TYPES + scope + r'!?: \S(?:.*\S)?', value) is not None)


def check_event(event):
    pr = event['pull_request']
    errors = []
    if not valid_header(pr['title'], pr=True):
        errors.append('PR title must use type(scope): subject, up to 100 characters.')
    base, head = pr['base']['sha'], pr['head']['sha']
    if not all(re.fullmatch(r'[0-9a-f]{40}', sha) for sha in (base, head)):
        raise ValueError('Invalid PR commit identity')
    result = subprocess.run(['git', 'log', '--format=%H%x00%s', f'{base}..{head}'],
                            check=True, text=True, capture_output=True)
    commits = result.stdout.splitlines()
    if not commits:
        errors.append('No proposed commits found.')
    for line in commits:
        sha, subject = line.split('\0', 1)
        if not valid_header(subject):
            # Do not interpret a contributor-controlled subject as a log command.
            errors.append(f'Commit {sha[:12]} must use type(scope): subject or type: subject, up to 100 characters.')
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f'PASS: PR title and {len(commits)} Conventional Commit header(s)')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('event', type=Path, help='GitHub pull_request event JSON')
    args = parser.parse_args()
    try:
        sys.exit(check_event(json.loads(args.event.read_text())))
    except (ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Cannot validate conventions: {error}\n')
