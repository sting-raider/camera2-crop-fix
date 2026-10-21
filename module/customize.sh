#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
[ "$ARCH" = arm64 ] || abort "Only arm64 is supported"
[ "$BOOTMODE" = true ] || abort "Install from the Magisk or APatch app"
# APatch reports a fixed MAGISK_VER_CODE of 27000, so it is gated on its own tools.
if [ "$APATCH" = true ]; then
  [ -x /data/adb/ap/bin/busybox ] && [ -x /data/adb/ap/bin/resetprop ] || abort "APatch busybox/resetprop not found"
else
  [ "$MAGISK_VER_CODE" -ge 30700 ] || abort "Magisk 30.7 or newer is required"
fi
(cd "$MODPATH" && sha256sum -c local-files.sha256) >/dev/null || abort "Package integrity check failed"
. "$MODPATH/profile.sh" || abort "Cannot read build profile"
[ "$(getprop ro.lineage.version)" = "$LINEAGE_VERSION" ] &&
  [ "$(getprop ro.build.display.id)" = "$DISPLAY_ID" ] &&
  [ "$(getprop ro.vendor.build.fingerprint)" = "$VENDOR_FINGERPRINT" ] || abort "Unsupported ROM build"
sha256sum -c "$MODPATH/dependencies.sha256" >/dev/null || abort "Unsupported camera libraries"
state=/data/adb/camera2_native_zoom_fix
[ ! -L "$state" ] || abort "State path must not be a symlink"
if [ ! -e "$state" ]; then mkdir -m 0700 "$state" || abort "Cannot create private state"; fi
[ "$(stat -c %u:%a "$state")" = 0:700 ] || abort "Unexpected state ownership or permissions"
backup="$state/original.$ORIGINAL"
[ ! -L "$backup" ] || abort "Original backup must not be a symlink"
if [ ! -e "$backup" ]; then
  [ "$(sha256sum /system/bin/cameraserver | awk '{print $1}')" = "$ORIGINAL" ] ||
    abort "Close camera apps, restore the previous crop module, then install again"
  cp /system/bin/cameraserver "$backup.tmp" || abort "Cannot save original image"
  chmod 0600 "$backup.tmp"
  [ "$(sha256sum "$backup.tmp" | awk '{print $1}')" = "$ORIGINAL" ] || abort "Original image changed during copy"
  mv "$backup.tmp" "$backup" || abort "Cannot finalize original backup"
fi
. "$MODPATH/patch.sh" || abort "Cannot load patch installer"
mkdir -p "$MODPATH/bin"
patch_image "$backup" "$MODPATH/bin/cameraserver.native" || abort "Cannot construct verified camera image"
sha256sum "$MODPATH/bin/cameraserver.native" | awk '{print $1}' > "$MODPATH/native.sha256"
(cd "$MODPATH" && sha256sum native.sha256 bin/cameraserver.native > generated-files.sha256) || abort "Cannot record generated integrity hashes"
set_perm_recursive "$MODPATH" 0 0 0700 0600
for script in "$MODPATH"/*.sh; do set_perm "$script" 0 0 0700; done
set_perm "$MODPATH/bin/cameraserver.native" 0 2000 0755
chcon u:object_r:cameraserver_exec:s0 "$MODPATH/bin/cameraserver.native" || abort "Cannot label camera image"
touch "$MODPATH/skip_mount"
ui_print "OnePlus 15 Camera2 Crop Fix installed. Reboot to finish."
ui_print "First install stays paused. Close camera apps, then use Action to enable."
ui_print "Updates preserve your enable request. Unsupported builds stay off."
