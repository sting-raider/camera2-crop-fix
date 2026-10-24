#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
MODDIR=$(cd "${0%/*}" && pwd -P) || exit 1
[ "$MODDIR" = /data/adb/modules/camera2_native_zoom_fix ] || exit 1
if [ "$APATCH" = true ]; then
  # APatch already runs action.sh as root in the init mount namespace.
  /data/adb/ap/bin/busybox sh "$MODDIR/control.sh" toggle; action_result=$?
  /data/adb/ap/bin/busybox sh "$MODDIR/control.sh" status
  exit "$action_result"
fi
# Explicit global namespace; command/path are constants, not user input.
exec /data/adb/magisk/magisk su -mm -c '/data/adb/magisk/busybox sh /data/adb/modules/camera2_native_zoom_fix/control.sh toggle; action_result=$?; /data/adb/magisk/busybox sh /data/adb/modules/camera2_native_zoom_fix/control.sh status; exit "$action_result"'
