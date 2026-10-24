## 1.0.1

- Fix an OTA first-boot false fault: wait up to two minutes for the userdata checkpoint to finish before activating. A pending checkpoint keeps correction off and preserves the existing enable request; it does not latch a permanent fault. If the wait expires, run `on` after boot.
- Manual activation during a pending checkpoint returns a temporary status. Action remains available to pause while boot activation waits.
- Native patch bytes, supported builds and integrity checks are unchanged. Host regression checks cover checkpoint completion, timeout and cancellation; first-OTA-boot device validation is still pending.

## 1.0.0

First stable release. It includes the unreleased 0.4.0-beta.2 changes below, plus APatch support and automatic updates.

- Automatic updates: Magisk and APatch check this module's `update.json` on the stable release channel. Beta users install 1.0.0 manually once.
- APatch 11039 or newer is supported alongside Magisk 30.7 or newer. Not device-tested on APatch. Under APatch, finish module installs, updates and removals with a full reboot, not Soft reboot.
- Uninstalling no longer leaves a persistent fault when the camera service has not started yet.
- Known issue: the first boot after a system OTA can latch a fault when `/data` is remounted for the userdata checkpoint. Check it with `control.sh status` and read [architecture and recovery](https://github.com/hackroid/camera2-crop-fix/blob/main/doc/architecture.md) before clearing it.

Builds and evidence:

Support these official LineageOS builds in one package: OnePlus 15T (PLZ110) `24.0-20261011-NIGHTLY-fairlady`, `24.0-20261014-NIGHTLY-fairlady`, `24.0-20261015-NIGHTLY-fairlady` and `24.0-20261022-NIGHTLY-fairlady`; OnePlus 15 `24.0-20261014-NIGHTLY-infiniti` and `24.0-20261021-NIGHTLY-infiniti`. Each build is accepted only with its own device's vendor fingerprint and camera HAL hash. The native patch source and the camera-service and system camera-library hash checks are unchanged; `camera.qcom.so` is checked against each device's own hash. A listed build with different camera files is still rejected at install and activation.

- fairlady 20261011: device-tested profile.
- fairlady 20261022: camera service and the three checked camera libraries are byte-identical to the 20261011 profile (official OTA). Device-tested after the OTA: unmodified, physical IDs 2 and 3 return crop2 as ratio 1 / 1024×768. With this package they return 2048×1536, the controller reports verified with no fault, and the correction re-arms after reboot.
- fairlady 20261014, 20261015: listed by exact version; their camera files were not extracted, so the on-device hash checks decide.
- infiniti 20261014, 20261021: the camera service, `libcamera_client.so` and `libcamera_metadata.so` are byte-identical to the 15T profile, so the same patch applies. `camera.qcom.so` and the vendor fingerprint are the OnePlus 15's own and are pinned (official OTAs). Not device-tested. The guard corrects only physical rear cameras `2` and `3` that report the 15T's 4096×3072 arrays and 5.59/12.19 mm focal lengths; other results pass through unchanged and status stays at `verified=0`.

## 0.4.0-beta.1

Initial public pre-release for OnePlus 15T (PLZ110), LineageOS `24.0-20261011-NIGHTLY-fairlady` only.

- Correct repeated crop metadata scaling for independently opened physical rear cameras 2 and 3, including quantized 10× and CUSTOM still requests.
- Toggle with Magisk Action; retain the requested state across reboot.
- Validate exact firmware/library identities and disable correction on a detected fault.
- Construct the patched image from the verified installed original; no complete system image is distributed.

Logical-camera automatic lens selection and application post-processing are outside this patch. Install this beta manually; automatic updates start with stable releases.
