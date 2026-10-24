#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
MODDIR=$(cd "${0%/*}" && pwd -P) || exit 1
[ "$MODDIR" = /data/adb/modules/camera2_native_zoom_fix ] || exit 1
if [ "$APATCH" = true ]; then
  # APatch already runs service.sh as root in the init mount namespace.
  if [ "$1" = watch ]; then
    exec /data/adb/ap/bin/busybox sh "$MODDIR/control.sh" watch
  fi
  exec /data/adb/ap/bin/busybox sh "$MODDIR/control.sh" boot
fi
if [ "$1" = watch ]; then
  exec /data/adb/magisk/busybox sh "$MODDIR/control.sh" watch
fi
exec /data/adb/magisk/magisk su -mm -c 'exec /data/adb/magisk/busybox sh /data/adb/modules/camera2_native_zoom_fix/control.sh boot'
