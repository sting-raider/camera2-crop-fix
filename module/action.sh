#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
MODDIR=$(cd "${0%/*}" && pwd -P) || exit 1
[ "$MODDIR" = /data/adb/modules/camera2_native_zoom_fix ] || exit 1
# Explicit global namespace; command/path are constants, not user input.
exec /data/adb/magisk/magisk su -mm -c '/data/adb/magisk/busybox sh /data/adb/modules/camera2_native_zoom_fix/control.sh toggle; action_result=$?; /data/adb/magisk/busybox sh /data/adb/modules/camera2_native_zoom_fix/control.sh status; exit "$action_result"'
