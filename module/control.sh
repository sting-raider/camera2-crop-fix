#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
if [ -x /data/adb/ap/bin/busybox ]; then
  BB=/data/adb/ap/bin/busybox
  resetprop() { /data/adb/ap/bin/resetprop "$@"; }
else
  BB=/data/adb/magisk/busybox
  resetprop() { /data/adb/magisk/magisk resetprop "$@"; }
fi
if [ "${ASH_STANDALONE:-0}" != 1 ]; then
  export ASH_STANDALONE=1
  exec "$BB" sh "$0" "$@"
fi
umask 077
MODDIR=$(cd "${0%/*}" && pwd -P) || exit 1
[ "$MODDIR" = /data/adb/modules/camera2_native_zoom_fix ] || { echo 'Installed canonical module path required' >&2; exit 1; }
[ "$(id -u)" = 0 ] || exit 1
STATE=/data/adb/camera2_native_zoom_fix
RUN="$STATE/run"
TARGET=/system/bin/cameraserver
PAYLOAD="$MODDIR/bin/cameraserver.native"
KEY=persist.camera.zoom_crop_fix
PIDKEY=persist.camera.zoom_crop_fix.pid
. "$MODDIR/profile.sh" || exit 1
CANDIDATE=$(cat "$MODDIR/native.sha256" 2>/dev/null)
case "$1" in on|pause|restore|toggle|boot|watch|status) MODE=$1;; *) echo 'on|pause|restore|toggle|status' >&2; exit 2;; esac
sha() { sha256sum "$1" | awk '{print $1}'; }
ns() { readlink "/proc/$1/ns/mnt"; }
birth() { awk '{print $22}' "/proc/$1/stat" 2>/dev/null; }
number() { case "$1" in *[!0-9]*|'') return 1;; esac; }
hash() { case "$1" in *[!0-9a-f]*|'') return 1;; esac; [ "${#1}" = 64 ]; }
label() { ls -Zd "$1" | awk '{for(i=1;i<=NF;i++) if($i~/^u:object_r:/) print $i}'; }
set_off() { resetprop -n "$KEY" 0 && [ "$(getprop "$KEY")" = 0 ]; }
note() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >> "$RUN/events.log"; }
fault() {
  set_off || echo 'Runtime OFF could not be confirmed' >&2
  rm -f "$STATE/ENABLE"
  if [ ! -e "$STATE/FAULT" ]; then
    : > "$STATE/FAULT" || echo 'Persistent fault placeholder could not be written' >&2
    { printf 'fault: %s\nboot=%s\npid=%s\nutc=%s\n' "$*" "$BOOT" "${PID:-unknown}" "$(date -u +%FT%TZ)"; } > "$STATE/.fault.$$" &&
      mv "$STATE/.fault.$$" "$STATE/FAULT"
  fi
  printf 'fault: %s\n' "$*" > "$RUN/status"
  note "fault: $*; no automatic retry"
  return 1
}
# A boot entry clears the persistent gate before acquiring any UI/phase lock,
# even if another operation or an incomplete state directory later rejects it.
if [ "$MODE" = boot ]; then
  set_off || { echo 'Boot runtime OFF could not be confirmed' >&2; exit 1; }
fi
if [ "$MODE" = status ]; then
  [ ! -L "$STATE" ] || { echo 'State path is a symlink; status refused' >&2; exit 1; }
  printf 'flag=%s pid_key=%s enable_request=%s\n' "$(getprop "$KEY")" "$(getprop "$PIDKEY")" "$(test -f "$STATE/ENABLE" && echo yes || echo no)"
  if [ -e "$STATE/FAULT" ]; then
    if [ -s "$STATE/FAULT" ]; then cat "$STATE/FAULT"; else echo 'FAULT latched; original reason unavailable'; fi
  fi
  [ ! -f "$RUN/status" ] || cat "$RUN/status"
  exit 0
fi
# Rollback/off never depend on version or package hashes.
[ ! -L "$STATE" ] || exit 1
if [ ! -d "$STATE" ]; then mkdir -m 0700 "$STATE" || exit 1; fi
[ "$(stat -c %u:%a "$STATE")" = 0:700 ] || exit 1
mkdir -p "$RUN" && chmod 0700 "$RUN" || exit 1
BOOT=$(cat /proc/sys/kernel/random/boot_id) || exit 1
INITNS=$(ns 1)
if [ "$(ns $$)" != "$INITNS" ] || [ -z "$INITNS" ]; then set_off; echo 'Use su -mm (Magisk) or run as APatch root; init namespace required' >&2; exit 1; fi
mount_id() { awk -v p="$TARGET" '$5==p{print $1}' /proc/self/mountinfo; }
data_mount() { awk '$5=="/data"{print $1" "$6" "$NF}' /proc/self/mountinfo; }
owned_flags() {
  options=$(awk -v p="$TARGET" '$5==p{print $6}' /proc/self/mountinfo)
  case ",$options," in *,nosuid,*|*,noexec,*) return 1;; esac
  case ",$options," in *,ro,*) ;; *) return 1;; esac
  [ "$(data_mount)" = "$(cat "$RUN/data.mount" 2>/dev/null)" ]
}
owned_bind() {
  [ -r "$RUN/bind" ] || return 1
  read -r owned_boot owned_ns owned_mount owned_inode < "$RUN/bind"
  [ "$owned_boot" = "$BOOT" ] && [ "$owned_ns" = "$INITNS" ] && number "$owned_mount" &&
    [ "$(mount_id)" = "$owned_mount" ] && [ "$(stat -c %d:%i "$TARGET")" = "$owned_inode" ]
}
policy() {
  [ "$(getenforce)" = Enforcing ] && [ "$(cat /sys/fs/selinux/enforce)" = 1 ] || return 1
  POLICY=$(sha /sys/fs/selinux/policy) && hash "$POLICY"
}
one_pid() {
  set -- $(pidof cameraserver 2>/dev/null)
  [ "$#" = 1 ] || return 1
  PID=$1; START=$(birth "$PID")
  number "$PID" && number "$START" && [ "$PID" -gt 0 ] &&
    [ "$(cat "/proc/$PID/attr/current" 2>/dev/null)" = u:r:cameraserver:s0 ] &&
    [ "$(ns "$PID")" = "$INITNS" ] && [ "$(readlink "/proc/$PID/exe")" = "$TARGET" ]
}
same_pid() {
  one_pid && [ "$PID:$START" = "$(cat "$RUN/accepted.pid" 2>/dev/null)" ] &&
    [ "$(stat -Lc %d:%i "/proc/$PID/exe")" = "$(cat "$RUN/accepted.inode" 2>/dev/null)" ]
}
read_native_state() {
  # Exact 16-byte root read. Failed access is never a request to relax policy.
  NATIVE_FAULT=unknown; VERIFIED=; COUNT2=; COUNT3=
  "$BB" dd if="/proc/$PID/mem" of="$RUN/.state.$$" bs=1 skip="$STATE_ADDRESS" count=16 2>/dev/null || { note "native-state read failed"; return 1; }
  [ "$(wc -c < "$RUN/.state.$$")" = 16 ] || return 1
  set -- $("$BB" od -An -tu4 -N16 "$RUN/.state.$$")
  rm -f "$RUN/.state.$$"
  [ "$#" = 4 ] || return 1
  for value in "$@"; do number "$value" || return 1; [ "$value" -le 4294967295 ] || return 1; done
  NATIVE_FAULT=$1; VERIFIED=$2; COUNT2=$3; COUNT3=$4
  [ "$VERIFIED" -le 1 ] && [ "$(birth "$PID")" = "$START" ]
}
review_process() {
  one_pid && [ "$(sha "/proc/$PID/exe")" = "$CANDIDATE" ] || return 1
  [ "$(stat -Lc %d:%i "/proc/$PID/exe")" = "$(stat -c %d:%i "$PAYLOAD")" ] || return 1
  cp "/proc/$PID/maps" "$RUN/maps.$PID" || return 1
  inode=$(stat -c %i "$PAYLOAD")
  device=$(stat -c %d "$PAYLOAD")
  major=$(( ((device >> 8) & 4095) | ((device >> 32) & 4294963200) ))
  minor=$(( (device & 255) | ((device >> 12) & 4294967040) ))
  BASE=; RX_OK=0; RW_OK=0
  while read -r range perms offset dev ino path; do
    case "$range:$offset:$dev:$ino" in *[!0-9a-fA-F:\ -]*) return 1;; esac
    [ "$ino" = "$inode" ] || continue
    devmajor=${dev%:*}; devminor=${dev#*:}
    [ "$((0x$devmajor)):$((0x$devminor))" = "$major:$minor" ] || continue
    case "$perms" in *w*x*) return 1;; esac
    if [ "$offset" = 00000000 ]; then BASE=${range%-*}; break; fi
  done < "$RUN/maps.$PID"
  [ -n "$BASE" ] || return 1
  ENTRY_ADDRESS=$((0x$BASE + ENTRY)); TEXT_END_ADDRESS=$((0x$BASE + TEXT_END))
  STATE_ADDRESS=$((0x$BASE + STATE_OFFSET))
  while read -r range perms offset dev ino path; do
    lo=$((0x${range%-*})); hi=$((0x${range#*-}))
    if [ "$ino" = "$inode" ]; then
      devmajor=${dev%:*}; devminor=${dev#*:}
      if [ "$((0x$devmajor)):$((0x$devminor))" = "$major:$minor" ]; then
        case "$perms" in *w*x*) return 1;; esac
        [ "$ENTRY_ADDRESS" -lt "$lo" ] || [ "$TEXT_END_ADDRESS" -gt "$hi" ] || [ "$perms" != r-xp ] || RX_OK=1
      fi
    fi
    rw_owned=0
    if [ "$ino" = 0 ]; then
      devmajor=${dev%:*}; devminor=${dev#*:}
      [ "$((0x$devmajor)):$((0x$devminor))" != 0:0 ] || rw_owned=1
    elif [ "$ino" = "$inode" ]; then
      devmajor=${dev%:*}; devminor=${dev#*:}
      [ "$((0x$devmajor)):$((0x$devminor))" != "$major:$minor" ] || rw_owned=1
    fi
    if [ "$rw_owned" = 1 ]; then
      [ "$STATE_ADDRESS" -lt "$lo" ] || [ "$((STATE_ADDRESS + 64))" -gt "$hi" ] || [ "$perms" != rw-p ] || RW_OK=1
    fi
  done < "$RUN/maps.$PID"
  [ "$RX_OK:$RW_OK" = 1:1 ] && read_native_state && [ "$NATIVE_FAULT" = 0 ] &&
    [ "$(birth "$PID")" = "$START" ] || return 1
  printf '%s:%s\n' "$PID" "$START" > "$RUN/accepted.pid"
  stat -Lc %d:%i "/proc/$PID/exe" > "$RUN/accepted.inode"
  printf '%s\n' "$STATE_ADDRESS" > "$RUN/state.address"
}
no_clients() {
  timeout 8 /system/bin/dumpsys media.camera > "$RUN/clients" 7>&- 8>&- 9>&- || return 1
  clients=$(awk '/^Active Camera Clients:/{p=1;next}p{gsub(/[[:space:]]/,"");s=s $0;if(index(s,"]")){print s;exit}}' "$RUN/clients")
  [ "$clients" = '[]' ]
}
verify_activation() {
  [ ! -e "$STATE/FAULT" ] && [ ! -e "$MODDIR/disable" ] && [ ! -e "$MODDIR/remove" ] &&
    [ -f "$MODDIR/skip_mount" ] && [ ! -e "$MODDIR/system" ] || return 1
  [ "$(readlink -f "$TARGET")" = "$TARGET" ] || return 1
  (cd "$MODDIR" && sha256sum -c local-files.sha256 && sha256sum -c generated-files.sha256) >> "$RUN/events.log" 2>&1 || return 1
  [ "$(getprop ro.lineage.version)" = "$LINEAGE_VERSION" ] &&
    [ "$(getprop ro.build.display.id)" = "$DISPLAY_ID" ] &&
    [ "$(getprop ro.vendor.build.fingerprint)" = "$VENDOR_FINGERPRINT" ] || return 1
  sha256sum -c "$MODDIR/dependencies.sha256" >> "$RUN/events.log" 2>&1 || return 1
  hash "$CANDIDATE" && [ "$(sha "$PAYLOAD")" = "$CANDIDATE" ] && [ "$(stat -c %u:%g:%a "$PAYLOAD")" = 0:2000:755 ] &&
    [ "$(label "$PAYLOAD")" = u:object_r:cameraserver_exec:s0 ] &&
    [ "$(label "$TARGET")" = u:object_r:cameraserver_exec:s0 ] || return 1
  policy
}
# 0=authenticated live watcher, 1=recorded watcher gone, 2=uncertain identity.
watcher_identity() {
  [ -r "$RUN/watcher.pid" ] || return 1
  read -r WP WS < "$RUN/watcher.pid"
  number "$WP" && number "$WS" && [ "$WP" -gt 0 ] || return 2
  [ -d "/proc/$WP" ] || return 1
  [ -r "/proc/$WP/stat" ] || return 2
  [ "$(awk '{print $3}' "/proc/$WP/stat")" != Z ] || return 1
  observed_birth=$(birth "$WP")
  number "$observed_birth" || { [ ! -d "/proc/$WP" ] && return 1; return 2; }
  [ "$observed_birth" = "$WS" ] || return 1
  tr '\0' '\n' < "/proc/$WP/cmdline" | grep -Fxq "$MODDIR/control.sh" || return 2
  tr '\0' '\n' < "/proc/$WP/cmdline" | grep -Fxq watch || return 2
  kill -0 "$WP" 2>/dev/null && return 0
  [ ! -d "/proc/$WP" ] && return 1
  return 2
}
watcher_alive() { watcher_identity; [ "$?" = 0 ]; }
stop_watcher() {
  watcher_identity; identity=$?
  case "$identity" in 2) return 1;; 0) kill -TERM "$WP" 2>/dev/null || return 1;; esac
  count=0
  while [ "$count" -lt 5 ]; do
    watcher_identity; identity=$?
    case "$identity" in 1) break;; 2) return 1;; esac
    sleep 1; count=$((count+1))
  done
  watcher_identity; identity=$?
  [ "$identity" = 1 ] || return 1
  rm -f "$RUN/watcher.pid" "$RUN/watcher.ready"
}
start_watcher() {
  watcher_identity; identity=$?
  case "$identity" in 0) return 0;; 2) return 1;; esac
  rm -f "$RUN/watcher.ready"
  nohup "$BB" setsid "$BB" sh "$MODDIR/service.sh" watch </dev/null >> "$RUN/events.log" 2>&1 7>&- 8>&- 9>&- &
  child=$!; child_start=$(birth "$child")
  number "$child_start" || return 1
  printf '%s %s\n' "$child" "$child_start" > "$RUN/watcher.pid"
  count=0
  while [ "$count" -lt 30 ]; do
    [ "$(cat "$RUN/watcher.ready" 2>/dev/null)" != "$child:$child_start" ] || { watcher_alive && return 0; }
    sleep 0.1; count=$((count+1))
  done
  return 1
}
activate() {
  set_off || return 1
  if [ "$(cat "$RUN/watch.stopped.boot" 2>/dev/null)" = "$BOOT" ]; then
    printf '%s\n' 'runtime OFF: watcher was signalled; reboot required before activation' > "$RUN/status"
    cat "$RUN/status" >&2
    return 75
  fi
  verify_activation || { fault 'activation/version/package/permission prerequisite rejected'; return 1; }
  BEFORE_POLICY=$POLICY
  # Decide whether a restart is needed before recording intent or creating a
  # bind. Ordinary busy clients are transient, not a persistent module fault.
  restart=1; old_pid=0; old_start=0
  set -- $(pidof cameraserver 2>/dev/null)
  case "$#" in
    0) ;;
    1)
      one_pid || { fault 'current camera PID identity uncertain'; return 1; }
      old_pid=$PID; old_start=$START; image=$(sha "/proc/$PID/exe")
      if [ "$image" = "$CANDIDATE" ]; then
        owned_bind && owned_flags && same_pid || { fault 'unexpected payload PID/bind; explicit fault review required'; return 1; }
        restart=0
      else
        [ "$image" = "$ORIGINAL" ] || { fault 'current camera image is unknown'; return 1; }
        if ! no_clients; then
          printf '%s\n' 'runtime OFF: close camera apps, then try again; no activation attempted' > "$RUN/status"
          cat "$RUN/status" >&2
          return 75
        fi
      fi;;
    *) fault 'ambiguous camera PID before activation'; return 1;;
  esac
  touch "$STATE/ENABLE" || return 1
  printf '%s\n' "$BOOT" > "$RUN/boot.id" || return 1
  if owned_bind; then
    owned_flags && [ "$(sha "$TARGET")" = "$CANDIDATE" ] || { fault 'owned payload content/flags changed'; return 1; }
  else
    [ -z "$(mount_id)" ] && [ "$(sha "$TARGET")" = "$ORIGINAL" ] &&
      [ "$(sha "/proc/1/root$TARGET")" = "$ORIGINAL" ] || { fault 'target is not the unmounted verified original'; return 1; }
    data_mount > "$RUN/data.mount"
    [ -s "$RUN/data.mount" ] || { fault 'cannot record /data parent flags'; return 1; }
    mount -o bind "$PAYLOAD" "$TARGET" || { fault 'explicit bind rejected'; return 1; }
    mid=$(mount_id); number "$mid" || { fault 'new bind is not unique'; return 1; }
    printf '%s %s %s %s\n' "$BOOT" "$INITNS" "$mid" "$(stat -c %d:%i "$TARGET")" > "$RUN/bind"
    owned_bind && [ "$(sha "/proc/1/root$TARGET")" = "$CANDIDATE" ] || { fault 'owned bind not visible in init'; return 1; }
    # /data is normally nosuid. Change only this already-owned file mount, so
    # init can perform the existing cameraserver_exec domain transition.
    mount -o remount,bind,ro,suid,exec "$TARGET" || { fault 'owned-file mount flags rejected'; return 1; }
    owned_bind && owned_flags || { fault 'owned target flags or /data parent changed'; return 1; }
  fi
  if [ "$restart" = 1 ]; then
    if [ "$old_pid" = 0 ]; then
      [ -z "$(pidof cameraserver 2>/dev/null)" ] || { fault 'camera PID appeared after activation preflight; no restart'; return 1; }
    else
      one_pid && [ "$PID:$START" = "$old_pid:$old_start" ] && [ "$(sha "/proc/$PID/exe")" = "$ORIGINAL" ] ||
        { fault 'camera PID changed after activation preflight; no restart'; return 1; }
    fi
    /system/bin/setprop ctl.restart cameraserver || { fault 'single init restart denied'; return 1; }
    count=0
    while [ "$count" -lt 15 ]; do
      set -- $(pidof cameraserver 2>/dev/null)
      if [ "$#" = 1 ] && [ "$1" != "$old_pid" ]; then break; fi
      sleep 1; count=$((count+1))
    done
    [ "$count" -lt 15 ] || { fault 'single restart did not yield a new PID'; return 1; }
  fi
  review_process && policy && [ "$POLICY" = "$BEFORE_POLICY" ] || { fault 'new payload PID/maps/native-state/policy review failed'; return 1; }
  printf '%s\n' "$POLICY" > "$RUN/policy.sha"
  start_watcher || { fault 'independent watcher did not become ready'; return 1; }
  watcher_alive && same_pid && owned_flags && read_native_state && [ "$NATIVE_FAULT" = 0 ] || { fault 'watcher/PID/mount/native state changed at final enable'; return 1; }
  resetprop -n "$PIDKEY" "$PID" && [ "$(getprop "$PIDKEY")" = "$PID" ] &&
    resetprop -n "$KEY" 1 && [ "$(getprop "$KEY")" = 1 ] || { fault 'PID/flag enable readback failed'; return 1; }
  printf 'armed pid=%s; waiting for native changed result\n' "$PID" > "$RUN/status"
  note "armed reviewed PID $PID:$START; no future automatic restart"
}
pause() {
  rm -f "$STATE/ENABLE"
  set_off || { fault 'pause could not confirm flag OFF'; return 1; }
  # UI lock7 remains held, so no on/boot can interleave while TERM cleanup
  # takes the short phase lock9 and repeats OFF after any earlier activation.
  flock -u 9
  stop_watcher; stopped=$?
  flock 9
  [ "$stopped" = 0 ] || { fault 'owned watcher did not stop'; return 1; }
  [ -e "$STATE/FAULT" ] || printf '%s\n' 'paused; runtime flag0; Action remains available' > "$RUN/status"
}
restore() {
  pause || note 'pause incomplete; only authenticated stop/owned rollback may continue'
  restore_mount=0; restore_start=0
  if [ -n "$(mount_id)" ]; then
    owned_bind || { fault 'restore refuses a foreign/uncertain bind'; return 1; }
    restore_mount=1; restore_start=1
  fi
  # An executable mount can remain EBUSY while its process is alive. For an
  # explicit restore only: authenticate it and clients, stop once, wait for no
  # PID, then unmount. Never restart the candidate to make rollback convenient.
  set -- $(pidof cameraserver 2>/dev/null)
  case "$#" in
    0)
      if [ "$restore_mount" = 0 ]; then
        [ "$(sha "$TARGET")" = "$ORIGINAL" ] && [ "$(sha "/proc/1/root$TARGET")" = "$ORIGINAL" ] &&
          [ "$(getprop init.svc.cameraserver)" = stopped ] || { fault 'absent camera PID requires verified original and stopped init state'; return 1; }
      fi
      restore_start=1;;
    1)
      one_pid || { fault 'restore current PID identity uncertain'; return 1; }
      image=$(sha "/proc/$PID/exe")
      case "$image" in
        "$ORIGINAL") ;;
        "$CANDIDATE")
          if [ "$restore_mount" = 1 ]; then
            [ "$(stat -Lc %d:%i "/proc/$PID/exe")" = "$owned_inode" ] || { fault 'restore payload inode is foreign'; return 1; }
          else
            same_pid || { fault 'restore refuses an unrecorded running payload'; return 1; }
          fi
          restore_start=1;;
        *) fault 'restore running image is unknown'; return 1;;
      esac
      if [ "$restore_start" = 1 ]; then
        no_clients || { fault 'restore requires known empty camera clients'; return 1; }
      fi;;
    *) fault 'restore camera PID ambiguous'; return 1;;
  esac
  if [ "$restore_start" = 1 ]; then
    # Even with no current PID, init may be between automatic respawns. Stop
    # the service explicitly and confirm its state before touching the mount.
    /system/bin/setprop ctl.stop cameraserver || { fault 'restore init stop denied'; return 1; }
    count=0
    while [ "$count" -lt 15 ]; do
      [ -z "$(pidof cameraserver 2>/dev/null)" ] && [ "$(getprop init.svc.cameraserver)" = stopped ] && break
      sleep 1; count=$((count+1))
    done
    [ "$count" -lt 15 ] || { fault 'restore camera stop not confirmed; no unmount/start'; return 1; }
  fi
  if [ "$restore_mount" = 1 ]; then
    owned_bind || { fault 'restore owned mount changed after stop; no unmount/start'; return 1; }
    umount "$TARGET" || { fault 'ordinary owned unmount failed after stop; no force/lazy/start'; return 1; }
  fi
  [ -z "$(mount_id)" ] && [ "$(sha "$TARGET")" = "$ORIGINAL" ] &&
    [ "$(sha "/proc/1/root$TARGET")" = "$ORIGINAL" ] || { fault 'original file view could not be verified'; return 1; }
  rm -f "$RUN/bind"
  if [ "$restore_start" = 1 ]; then
    /system/bin/setprop ctl.start cameraserver || { fault 'original file restored but init start denied'; return 1; }
    count=0
    while [ "$count" -lt 15 ]; do
      if one_pid && [ "$(getprop init.svc.cameraserver)" = running ] && [ "$(sha "/proc/$PID/exe")" = "$ORIGINAL" ]; then break; fi
      sleep 1; count=$((count+1))
    done
    [ "$count" -lt 15 ] || { fault 'original file restored but original PID not verified'; return 1; }
  fi
  rm -f "$RUN/accepted.pid" "$RUN/accepted.inode" "$RUN/state.address"
  set_off || { fault 'original restored but runtime flag reset remains unconfirmed'; return 1; }
  printf '%s\n' 'restored original; runtime OFF; any persistent FAULT remains blocked' > "$RUN/status"
  note 'owned bind removed; original file/process restored through stop-unmount-start'
}
record_watcher_exit() {
  [ -e "$STATE/ENABLE" ] && [ ! -e "$STATE/FAULT" ] || return 0
  case "${WATCH_SIGNAL:-}" in
    TERM|INT|HUP)
      # A readable sys.powerctl property cannot reliably identify shutdown.
      # A shutdown signal is indistinguishable from a live external signal:
      # fail OFF and prohibit same-boot retry, but preserve next-boot intent.
      # Real integrity/native faults remain persistent FAULTs instead.
      printf '%s\n' "$BOOT" > "$RUN/watch.stopped.boot" || { fault 'cannot record signalled watcher stop'; return 1; }
      printf 'watcher received %s; runtime OFF; activation blocked this boot\n' "$WATCH_SIGNAL" > "$RUN/status"
      note "watcher signal=$WATCH_SIGNAL; runtime OFF; enable intent preserved; same-boot activation blocked"
      ;;
    *) fault 'watcher exited while enable was requested';;
  esac
}
watch() {
  exec 8>"$RUN/watch.lock"; flock -n 8 || exit 1
  # Ready precedes only the parent's final enable. TERM waits behind the same
  # phase lock, then clears OFF again, so an in-flight on cannot re-enable late.
  exec 9>"$RUN/lock"
  watch_cleanup() {
    set_off
    flock 9
    set_off
    record_watcher_exit
    if [ "$(cat "$RUN/watcher.ready" 2>/dev/null)" = "$$:$(birth $$)" ]; then
      rm -f "$RUN/watcher.ready" "$RUN/watcher.pid"
    fi
    flock -u 9
  }
  trap watch_cleanup EXIT
  trap 'WATCH_SIGNAL=TERM; exit 0' TERM
  trap 'WATCH_SIGNAL=INT; exit 0' INT
  trap 'WATCH_SIGNAL=HUP; exit 0' HUP
  printf '%s:%s\n' "$$" "$(birth $$)" > "$RUN/watcher.ready"
  ticks=0
  while :; do
    sleep 2
    flock 9
    if [ ! -e "$STATE/ENABLE" ] || [ -e "$STATE/FAULT" ] || [ -e "$MODDIR/disable" ] || [ -e "$MODDIR/remove" ]; then
      if [ -e "$MODDIR/disable" ] || [ -e "$MODDIR/remove" ]; then rm -f "$STATE/ENABLE"; fi
      set_off; flock -u 9; exit 0
    fi
    owned_bind && owned_flags && same_pid || { fault 'unexpected PID/domain/exe/namespace/bind flags; no retry'; flock -u 9; exit 1; }
    STATE_ADDRESS=$(cat "$RUN/state.address")
    number "$STATE_ADDRESS" && read_native_state && [ "$NATIVE_FAULT" = 0 ] || { fault "native-state read/fault rejection code=${NATIVE_FAULT:-unknown}"; flock -u 9; exit 1; }
    [ "$(getprop "$PIDKEY")" = "$PID" ] && [ "$(getprop "$KEY")" = 1 ] || { fault 'enabled PID/flag changed externally'; flock -u 9; exit 1; }
    ticks=$((ticks+1))
    if [ "$ticks" -ge 15 ]; then policy && [ "$POLICY" = "$(cat "$RUN/policy.sha")" ] || { fault 'policy/enforcing audit changed'; flock -u 9; exit 1; }; ticks=0; fi
    printf 'pid=%s verified=%s changed_id2=%s changed_id4=%s fault=0\n' "$PID" "$VERIFIED" "$COUNT2" "$COUNT3" > "$RUN/status"
    flock -u 9
  done
}
[ "$MODE" != watch ] || { watch; exit $?; }
exec 7>"$RUN/ui.lock"; flock -n 7 || { echo 'Another UI operation is running' >&2; exit 75; }
exec 9>"$RUN/lock"; flock -n 9 || { echo 'Another control operation is running' >&2; exit 75; }
if [ "$MODE" = boot ]; then
  set_off || { fault 'boot could not confirm default runtime OFF'; exit 1; }
  [ -e "$STATE/ENABLE" ] && [ ! -e "$STATE/FAULT" ] || exit 0
  [ "$(cat "$RUN/boot.id" 2>/dev/null)" != "$BOOT" ] || { fault 'boot service already processed this boot; no second attempt'; exit 1; }
  [ -z "$(mount_id)" ] || { fault 'unexpected pre-existing bind at boot; ownership retained'; exit 1; }
  # Bind ownership cannot survive reboot; keep fault/intent, discard old runtime.
  rm -f "$RUN/bind" "$RUN/accepted.pid" "$RUN/accepted.inode" "$RUN/watcher.pid" "$RUN/watcher.ready"
  MODE=on
fi
if [ "$MODE" = toggle ]; then
  if [ -e "$STATE/ENABLE" ] || [ "$(getprop "$KEY")" = 1 ]; then MODE=pause; else MODE=on; fi
fi
case "$MODE" in on) activate;; pause) pause;; restore) restore;; esac
