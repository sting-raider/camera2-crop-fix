#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a self-contained Magisk patch ZIP without distributing a system image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Elf:
    def __init__(self, data):
        require(data[:6] == b'\x7fELF\x02\x01', 'Expected little-endian ELF64')
        require(struct.unpack_from('<H', data, 18)[0] == 183, 'Expected AArch64')
        self.data = data
        self.kind = struct.unpack_from('<H', data, 16)[0]
        phoff, shoff = struct.unpack_from('<QQ', data, 32)
        phsize, phnum, shsize, shnum, shstr = struct.unpack_from('<HHHHH', data, 54)
        require(phsize == 56 and shsize == 64, 'Unexpected ELF table sizes')
        self.ph = [struct.unpack_from('<IIQQQQQQ', data, phoff + i * phsize) for i in range(phnum)]
        self.sh = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * shsize) for i in range(shnum)]
        names = self.section_data(self.sh[shstr])
        self.sections = [(names[s[0]:names.index(b'\0', s[0])].decode(), s) for s in self.sh]

    def section_data(self, section):
        return self.data[section[4]:section[4] + section[5]]

    def symbol(self, wanted):
        found = []
        for _, section in self.sections:
            if section[1] != 2:
                continue
            strings = self.section_data(self.sh[section[6]])
            for offset in range(section[4], section[4] + section[5], 24):
                n, _, _, index, value, _ = struct.unpack_from('<IBBHQQ', self.data, offset)
                name = strings[n:strings.index(b'\0', n)].decode()
                require(index != 0 or not name, 'Unresolved native symbol: ' + name)
                if name == wanted:
                    found.append(value)
        require(found and len(set(found)) == 1, 'Missing/ambiguous symbol: ' + wanted)
        return found[0]


def compile_native(build, cc, linker):
    objects = []
    for name in ('entry.S', 'guard.c', 'provider.c'):
        output = build / (Path(name).stem + '.o')
        subprocess.run([cc, '--target=aarch64-linux-android', '-O2', '-ffreestanding', '-fPIC',
                        '-mno-outline-atomics', '-fno-stack-protector', '-fno-builtin',
                        '-ffp-contract=off', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
                        '-Wall', '-Wextra', '-Werror', '-c', str(ROOT/'src'/name), '-o', str(output)], check=True)
        objects.append(str(output))
    command = [linker]
    if Path(linker).name == 'rust-lld':
        command += ['-flavor', 'gnu']
    elf = build/'native.elf'
    subprocess.run(command + ['-m', 'aarch64elf', '--build-id=none', '--no-undefined', '--no-relax',
                              '--no-dynamic-linker', '-static', '-T', str(ROOT/'src/layout.ld'),
                              '-o', str(elf), *objects], check=True)
    return Elf(elf.read_bytes())


def patch_regions(elf, profile):
    entry, state = profile['entry'], profile['state']
    require(elf.kind == 2, 'Payload must be fully linked')
    require(not any(p[0] in (2, 3) or (p[0] == 1 and p[1] & 3 == 3) for p in elf.ph),
            'Dynamic loading and writable executable segments are forbidden')
    require(elf.symbol('zoom_fix_entry') == entry and elf.symbol('zoom_fix_state') == state,
            'Native entry/state moved')
    aliases = {'zoom_fix_original_mapper': profile['original_mapper'],
               'zoom_fix_find_ro_entry': 0x3901c0, 'zoom_fix_update_i32': 0x38df30,
               'zoom_fix_property_get': 0x391880, 'zoom_fix_getpid': 0x38dda0}
    for name, value in aliases.items():
        require(elf.symbol(name) == value, 'Changed ABI alias: ' + name)
    code = bytearray(profile['rx_limit'] - entry)
    occupied = set()
    end, state_end = entry, state
    for name, s in elf.sections:
        _, kind, flags, address, offset, size, *_ = s
        require(not (kind in (4, 6, 9, 11) and size), 'Unexpected dynamic/relocation section: ' + name)
        if not flags & 2 or not size:
            continue
        if flags & 1:
            require(kind == 8 and flags == 3 and address == state and size == profile['state_size'],
                    'Unexpected writable native state')
            state_end = address + size
        else:
            require(kind != 8 and not flags & ~(2 | 4 | 16 | 32) and
                    entry <= address < address + size <= profile['rx_limit'], 'Native code exceeds reserved gap')
            positions = set(range(address, address + size))
            require(not occupied & positions, 'Overlapping native sections')
            occupied |= positions
            code[address-entry:address-entry+size] = elf.data[offset:offset+size]
            end = max(end, address + size)
    end = (end + 15) & ~15
    require(state_end == state + profile['state_size'] and end > entry, 'Missing code/state')
    require(struct.unpack_from('<I', code)[0] == 0xaa1503e4, 'Entry must preserve x21 argument forwarding')
    tail = struct.unpack_from('<I', code, 4)[0]
    delta = tail & 0x3ffffff
    if delta & 0x2000000:
        delta -= 0x4000000
    require(tail & 0xfc000000 == 0x14000000 and entry+4+delta*4 == elf.symbol('zoom_guarded_c_wrapper'),
            'Unexpected entry branch')
    call = profile['callsite']
    branch = 0x94000000 | (((entry - call) // 4) & 0x3ffffff)
    regions = [(call, struct.pack('<I', branch)),
               (profile['rx_header_offset']+32, struct.pack('<QQ', end-profile['rx_start'], end-profile['rx_start'])),
               (profile['rw_header_offset']+40, struct.pack('<Q', state_end-profile['rw_start'])),
               (entry, bytes(code[:end-entry]))]
    return regions, end


def apply_regions(original, profile, regions):
    require(len(original) == profile['original_size'] and sha(original) == profile['original_sha256'],
            'Unsupported original cameraserver')
    require(not any(original[0x3918f0:profile['rx_limit']]), 'Original code gap is occupied')
    result = bytearray(original)
    for offset, data in regions:
        result[offset:offset+len(data)] = data
    require(len(result) == len(original), 'Unexpected image resize')
    return bytes(result)


def dependency_map(dependencies):
    require(isinstance(dependencies, dict) and all(
        isinstance(path, str) and re.fullmatch(r'/[!-~]+', path) and
        isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) for path, digest in dependencies.items()),
        'Invalid dependency hashes')
    return dependencies


def devices(profile):
    require(not {'lineage_version', 'lineage_versions', 'vendor_fingerprint'} & set(profile),
            'List builds per device under devices')
    shared = dependency_map(profile.get('dependencies'))
    entries = profile.get('devices')
    require(isinstance(entries, list) and entries, 'Missing device list')
    codenames, versions = [], []
    for device in entries:
        require(isinstance(device, dict) and set(device) ==
                {'name', 'codename', 'lineage_versions', 'vendor_fingerprint', 'dependencies'}, 'Unexpected device keys')
        codename, listed = device['codename'], device['lineage_versions']
        require(isinstance(codename, str) and re.fullmatch(r'[a-z0-9]+', codename), 'Invalid device codename')
        require(isinstance(listed, list) and listed and
                all(isinstance(version, str) and re.fullmatch(r'24\.0-[0-9]{8}-NIGHTLY-' + codename, version)
                    for version in listed), 'Invalid LineageOS version allowlist')
        require(isinstance(device['vendor_fingerprint'], str) and re.fullmatch(r'[!-~]+', device['vendor_fingerprint']),
                'Invalid vendor fingerprint')
        require(not set(shared) & set(dependency_map(device['dependencies'])), 'Dependency listed twice')
        codenames.append(codename)
        versions += listed
    require(len(codenames) == len(set(codenames)), 'Duplicate device codename')
    require(len(versions) == len(set(versions)), 'Duplicate LineageOS version')
    return entries


def build_list(targets):
    return ''.join(f'{version} {device["vendor_fingerprint"]} {device["codename"]}\n'
                   for device in targets for version in device['lineage_versions'])


def dependency_lists(profile, targets):
    return {device['codename']: ''.join(f'{digest}  {path}\n' for path, digest in
                                        {**profile['dependencies'], **device['dependencies']}.items())
            for device in targets}


def build_package(args):
    profile = json.loads((ROOT/'profile.json').read_text())
    targets = devices(profile)
    build = ROOT/'build'
    build.mkdir(exist_ok=True)
    elf = compile_native(build, args.cc, args.ld)
    regions, end = patch_regions(elf, profile)
    stage = build/'module'
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(ROOT/'module', stage)
    payload, plan = bytearray(), []
    for offset, data in regions:
        plan.append(f'{len(payload)} {offset} {len(data)}\n')
        payload.extend(data)
    (stage/'patch.bin').write_bytes(payload)
    (stage/'patch.plan').write_text(''.join(plan))
    facts = {'ORIGINAL': profile['original_sha256'], 'ORIGINAL_SIZE': profile['original_size'],
             'DISPLAY_ID': profile['display_id'], 'ENTRY': hex(profile['entry']),
             'TEXT_END': hex(end), 'STATE_OFFSET': hex(profile['state']), 'PATCH_SIZE': len(payload)}
    (stage/'profile.sh').write_text('# Generated from profile.json and the linked payload.\n' +
                                  ''.join(f'{key}={shlex.quote(str(value))}\n' for key, value in facts.items()))
    (stage/'builds').write_text(build_list(targets))
    for codename, listing in dependency_lists(profile, targets).items():
        (stage/f'dependencies.{codename}.sha256').write_text(listing)
    props = dict(line.split('=', 1) for line in (stage/'module.prop').read_text().splitlines())
    version = props['version']
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.]+)?', version), 'Invalid version')
    repo = args.repository or os.environ.get('GITHUB_REPOSITORY', 'hackroid/camera2-crop-fix')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo), 'Expected owner/repository')
    if '-' not in version:
        with (stage/'module.prop').open('a') as file:
            file.write(f'updateJson=https://github.com/{repo}/releases/latest/download/update.json\n')
    shutil.copyfile(ROOT/'LICENSE', stage/'LICENSE')
    checked = sorted(p for p in stage.iterdir() if p.is_file() and p.name != 'customize.sh')
    (stage/'local-files.sha256').write_text(''.join(f'{sha(p.read_bytes())}  {p.name}\n' for p in checked))
    for script in stage.glob('*.sh'):
        subprocess.run(['/bin/sh', '-n', str(script)], check=True)
    dist = ROOT/'dist'
    dist.mkdir(exist_ok=True)
    filename = f'camera2-crop-fix-{version}.zip'
    output = dist/filename
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.iterdir()):
            require(path.is_file(), 'Unexpected nested package content')
            info = zipfile.ZipInfo(path.name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100700 if path.suffix == '.sh' else 0o100600) << 16
            archive.writestr(info, path.read_bytes())
    (dist/'SHA256SUMS').write_text(f'{sha(output.read_bytes())}  {filename}\n')
    (dist/'update.json').write_text(json.dumps({'version': version, 'versionCode': int(props['versionCode']),
        'zipUrl': f'https://github.com/{repo}/releases/download/v{version}/{filename}',
        'changelog': f'https://github.com/{repo}/releases/download/v{version}/changelog.md'}, indent=2)+'\n')
    shutil.copyfile(ROOT/'doc/release-notes.md', dist/'changelog.md')
    report = {'version': version, 'native_sha256': sha(elf.data), 'text_end': hex(end),
              'patch_bytes': len(payload), 'zip_sha256': sha(output.read_bytes())}
    if args.original:
        image = apply_regions(args.original.read_bytes(), profile, regions)
        (build/'cameraserver.native').write_bytes(image)
        report['reconstructed_sha256'] = sha(image)
    (build/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('CC', 'clang'))
    parser.add_argument('--ld', default=os.environ.get('LD_LLD', 'ld.lld'))
    parser.add_argument('--repository')
    parser.add_argument('--original', type=Path, help='Optional local image for exact reconstruction checks; never included in ZIP')
    arguments = parser.parse_args()
    try:
        build_package(arguments)
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Build failed: {error}\n')
