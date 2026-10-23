# OnePlus 15T Camera2 Crop Fix

[简体中文](README-CN.md)

> **Upstream bug tracking:** [LineageOS/issues#853](https://github.com/LineageOS/issues/issues/853)
>
> Follow the upstream report for investigation and resolution status.

A reversible Magisk module that corrects repeated crop metadata scaling on the **OnePlus 15T (PLZ110)** with the supported LineageOS builds. It fixes the mismatch between preview and still-photo magnification on independently opened physical rear cameras, including the crop-size failure at 10×.

**Pre-release. Only the listed build identities are supported.** Other builds are rejected, even if their version names look similar.

## Requirements

| Component | Supported configuration |
| --- | --- |
| Device | OnePlus 15T / PLZ110 |
| LineageOS | `24.0-20261011-NIGHTLY-fairlady`<br>`24.0-20261014-NIGHTLY-fairlady`<br>`24.0-20261015-NIGHTLY-fairlady`<br>`24.0-20261022-NIGHTLY-fairlady` |
| Build ID | `CP2A.260605.016` |
| Camera paths | Physical rear camera IDs `2` and `3` |
| Root manager | Magisk 30.7, tested; newer versions must pass the same checks |

The installer and runtime also verify the exact original camera service and camera-library hashes. See [profile.json](profile.json). KernelSU and APatch are not supported by this package.

## Install and use

1. Download the module ZIP from [Releases](https://github.com/hackroid/camera2-crop-fix/releases), not GitHub's source-code ZIP.
2. Install it in **Magisk → Modules → Install from storage**, then reboot.
3. Close camera applications. Open this module in Magisk and tap **Action** to enable correction.
4. Tap **Action** again to pause. The requested state is retained across reboot.

`flag=1` means enabled; `flag=0` means paused. `verified=0` means this camera-service process has not yet processed a matching result. An initial activation may restart the camera service; pausing/resuming the same accepted process does not.

First installation stays paused. Updates retain your enable request. Beta releases are installed manually; stable releases will support Magisk's update mechanism.

### Remove or restore

Remove the module in Magisk and reboot to return to the original system image. The module uses a temporary file bind and never writes the system partition.

To restore immediately, close camera applications and run:

```sh
su -mm -c 'sh /data/adb/modules/camera2_native_zoom_fix/control.sh restore'
```

A fault disables correction and blocks automatic retry. System or library updates require a newly validated profile. Read [architecture and recovery](doc/architecture.md) before clearing any fault state.

## Scope

- Corrects guarded crop metadata for independently opened physical rear cameras `2` and `3`.
- Covers zoom rounding at 10× and supported photo/preview capture intents.
- Preserves the original mapper call and return value.
- Uses native code backed by a verified file; requires no added SELinux rules, Frida, Zygisk or Vector.

Automatic lens selection through logical camera `0`, application lens selection and application post-processing are outside this module's scope. This is not a universal camera or image-quality fix.

## Build and contribute

See the [development workflow](.github/CONTRIBUTING.md), [building and testing](doc/building.md) and [release setup](doc/releasing.md). A release ZIP contains a small native patch; the installer reconstructs the camera service from the verified original already on the device. Complete system/vendor binaries, photos and diagnostic logs are not distributed.

Please fork and PR if you want to contribute.

Licensed under [Apache-2.0](LICENSE).
