#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
MODDIR=$(cd "${0%/*}" && pwd -P) || exit 1
[ "$MODDIR" = /data/adb/modules/camera2_native_zoom_fix ] || exit 1
BB=/data/adb/magisk/busybox
[ ! -x /data/adb/ap/bin/busybox ] || BB=/data/adb/ap/bin/busybox
if [ "$1" = watch ]; then
  exec "$BB" sh "$MODDIR/control.sh" watch
fi
# APatch already runs service.sh as root in the init mount namespace.
[ "$BB" = /data/adb/magisk/busybox ] || exec "$BB" sh "$MODDIR/control.sh" boot
exec /data/adb/magisk/magisk su -mm -c 'exec /data/adb/magisk/busybox sh /data/adb/modules/camera2_native_zoom_fix/control.sh boot'
