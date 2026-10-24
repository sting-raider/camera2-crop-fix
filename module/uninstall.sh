#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
if [ "$APATCH" = true ]; then
  # APatch already runs uninstall.sh as root in the init mount namespace.
  exec /data/adb/ap/bin/busybox sh /data/adb/modules/camera2_native_zoom_fix/control.sh restore
fi
/data/adb/magisk/magisk su -mm -c '/data/adb/magisk/busybox sh /data/adb/modules/camera2_native_zoom_fix/control.sh restore'
