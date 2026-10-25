# Architecture and recovery

## Correction

On the supported physical rear camera paths, vendor results contain crop coordinates already scaled for the requested zoom. The framework's `ZoomRatioMapper` then scales them again. Pixels and reported geometry disagree; at 10× the reported crop can fall below a consumer's minimum crop size.

The native guard expands a recognized crop around the active-array center before calling the original mapper exactly once. It validates camera identity, metadata type/count, active/pre-correction arrays, zoom, focal length, crop geometry, capture intent, stabilization and unsupported override modes. Other results pass through. The physical subresult callback is untouched.

The entry and ABI addresses are specific to [the supported profile](../profile.json). Each listed device gets its own build of the guard. Its `telephoto_camera_id` selects the rear camera that must report the 12.19 mm telephoto focal length: `3` on the OnePlus 15T, `4` on the OnePlus 15, where `3` is the ultra-wide. The builds must share one patch layout; only their camera-ID instructions differ. The linker places new code in a verified executable alignment gap and a 64-byte state block in existing writable space. Only the primary mapper callsite and the required segment sizes change. No new dynamic imports, dynamic relocations, writable executable mappings or executable-memory permission are introduced.

## Installation and runtime

The ZIP contains newly built patch bytes for each device, a shared patch plan, scripts and their checksums. Installation validates the device properties, original image and camera-library hashes, then selects the patch for the matched device. It saves a private original at `/data/adb/camera2_native_zoom_fix/original.<sha256>` and constructs the patched image inside the module. This backup also allows later updates while an existing module bind is active. Generated image hashes are recorded at installation; package hashes protect the distributed patch and scripts.

First activation checks the init mount namespace, current camera clients, Enforcing state, payload identity, mapped regions and process domain. It records ownership of one file bind and changes only that file bind to `ro,suid,exec`; the parent `/data` mount is not changed. An empty client list is required before restarting the service. The native enable gate accepts only the reviewed process PID.

On boot, activation waits up to two minutes for vold's read-only `checkpoint needsCheckpoint` query to return false before recording its mount baseline. The query shares vold's checkpoint commit lock, so it waits for the normal userdata remount to finish after an OTA. Each query has a two-second timeout. Waiting holds no UI/phase locks, so Action can pause it. A pending or unavailable checkpoint query leaves correction off without latching a fault or deleting an existing enable request; run `on` after boot to retry if the wait expires. Ordinary boots without a pending checkpoint activate immediately. Subsequent mount changes still fail the integrity checks.

Action toggles enable/pause. A separately identified watcher validates process birth, namespace, bind identity, native fault state and SELinux policy. Identity/native/policy failures turn correction off and latch the first persistent `FAULT`; the watcher never restarts the camera service or retries activation.

A watcher receiving TERM/INT/HUP turns correction off, blocks same-boot activation and preserves the next-boot enable request. A readable `sys.powerctl` property cannot reliably distinguish shutdown from an external signal. An unsignalled exit while enabled remains a persistent fault. Explicit pause removes the enable request before stopping its watcher.

## Recovery

- Pause clears the correction gate and enable request; it leaves the known native process and bind available for a fast resume.
- Restore authenticates the owned bind/process and an empty client list, stops the service, performs an ordinary unmount, verifies the original, then starts the original service. No lazy or forced unmount is used.
- Disabling/removing the module and rebooting discards the temporary bind. The original system partition was never modified.
- State and the original backup are private to root and retained outside the module directory. Reinstalling does not silently erase a fault.

To inspect status:

```sh
su -mm -c 'sh /data/adb/modules/camera2_native_zoom_fix/control.sh status'
```

For a latched fault, close camera applications, pause/restore, and inspect `/data/adb/camera2_native_zoom_fix/FAULT` and `run/events.log`. Resolve the cause before explicitly archiving/clearing that file and enabling a fresh process. Do not clear an incompatibility fault just to bypass an unsupported ROM. A process's native fault latch cannot be cleared by deleting a file.
