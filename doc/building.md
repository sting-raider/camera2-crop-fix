# Building and testing

Python 3.10+, Clang and LLVM LLD are required. No Android SDK, NDK, phone, vendor library or complete system image is required to build a ZIP. CI uses Ubuntu 24.04 with `clang-18` and `lld-18` from Ubuntu's package repository.

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends clang-18 lld-18
CC=clang-18 python3 tools/test.py
CC=clang-18 LD_LLD=ld.lld-18 python3 tools/build.py
```

Output is written to ignored `build/` and `dist/` directories. Upload the ZIP, `SHA256SUMS`, `changelog.md` and `update.json` from `dist/` when releasing. Do not upload `build/` or a reconstructed system image.

The build uses only Python's standard library and the selected local compiler/linker. It does not download or execute remote scripts. Set `CC` and `LD_LLD`, or use `--cc` and `--ld`, for other LLVM installations. A local `rust-lld` can be selected as a GNU-flavor LLD alternative.

The native linker fixes entry/state/ABI addresses. The packager rejects unresolved symbols, dynamic loader state, relocations, overlapping sections, executable writable segments and code outside the reserved gap. The installer requires the exact original image and dependencies in `profile.json`; these checks are not optional porting switches.

To validate byte-for-byte reconstruction against a local copy of the supported original:

```sh
CC=clang LD_LLD=ld.lld python3 tools/build.py --original /path/to/cameraserver.original
```

That optional input and the reconstructed output stay local and are never included in the ZIP. Different LLVM versions can produce different native bytes; the same toolchain and inputs are required for byte reproducibility. Before publishing, test the exact CI-built ZIP on the supported device, including enable/pause, restart persistence and original restore. Host checks verify metadata guards, PID/fault logic, concurrent counters, watcher exits and installer bounds; they do not replace device lifecycle testing.

A port needs a new verified profile, including the device's telephoto camera ID, ABI/layout analysis and device validation. Renaming the build or removing checksum checks does not create support for another ROM.
