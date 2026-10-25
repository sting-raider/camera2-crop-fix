#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Source this file only after validating package checksums and profile.sh,
# and after build_supported has set CODENAME to select this device's payload.
patch_image() {
  original=$1; output=$2
  case "$CODENAME" in ''|*[!a-z0-9]*) return 1;; esac
  payload="$MODPATH/patch.$CODENAME.bin"
  [ -f "$payload" ] && [ "$(wc -c < "$payload")" -eq "$PATCH_SIZE" ] || return 1
  [ "$(wc -c < "$original")" -eq "$ORIGINAL_SIZE" ] &&
    [ "$(sha256sum "$original" | awk '{print $1}')" = "$ORIGINAL" ] || return 1
  cp "$original" "$output.tmp" || return 1
  [ "$(sha256sum "$output.tmp" | awk '{print $1}')" = "$ORIGINAL" ] || return 1
  patch_count=0
  while read -r source_offset target_offset length extra; do
    case "$source_offset:$target_offset:$length" in *[!0-9:]*|::*|:*|*:) return 1;; esac
    [ -z "$extra" ] && [ "$length" -gt 0 ] &&
      [ "$((source_offset + length))" -le "$PATCH_SIZE" ] &&
      [ "$((target_offset + length))" -le "$ORIGINAL_SIZE" ] || return 1
    dd if="$payload" of="$output.tmp" bs=1 skip="$source_offset" seek="$target_offset" count="$length" conv=notrunc 2>/dev/null || return 1
    patch_count=$((patch_count+1))
  done < "$MODPATH/patch.plan"
  [ "$patch_count" = 4 ] && [ "$(wc -c < "$output.tmp")" -eq "$ORIGINAL_SIZE" ] || return 1
  mv "$output.tmp" "$output"
}
