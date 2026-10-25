/* SPDX-License-Identifier: Apache-2.0 */
#define ZOOM_FIX_PROVIDER_HOST_TEST 1
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include "../src/provider.c"

static const char *enable = "1", *pid_text = "2199";
static int current_pid = 2199, length_override = -1;
const u8 *zoom_test_image_base(void) { return 0; }
int zoom_fix_getpid(void) { return current_pid; }
int zoom_fix_property_get(const char *key, char *out) {
    const char *value = strcmp(key, "persist.camera.zoom_crop_fix.pid") == 0 ? pid_text : enable;
    size_t length = strlen(value);
    memcpy(out, value, length + 1);
    return strcmp(key, "persist.camera.zoom_crop_fix.pid") == 0 && length_override >= 0
        ? length_override : (int)length;
}
static void reset(void) {
    memset(&zoom_fix_state, 0, sizeof(zoom_fix_state));
    zoom_fix_state.versions_verified = 1;
    enable = "1"; pid_text = "2199"; current_pid = 2199; length_override = -1;
}
static void *counter(void *arg) {
    for (int i = 0; i < 10000; ++i) zoom_fix_note_changed((u32)(uptr)arg);
    return 0;
}
int main(void) {
    reset(); assert(zoom_fix_runtime_permitted() == 1);
    const char *invalid[] = {"", "0", "02199", "+2199", "-2199", "2199 ", " 2199",
                            "2199x", "2200", "2147483648", "4294967295", "99999999999999999999"};
    for (unsigned i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        reset(); pid_text = invalid[i];
        assert(!zoom_fix_runtime_permitted() && !zoom_fix_state.first_fault);
    }
    reset(); length_override = 3; assert(!zoom_fix_runtime_permitted());
    reset(); current_pid = 0; assert(!zoom_fix_runtime_permitted());
    reset(); pid_text = "2147483647"; current_pid = 2147483647;
    assert(zoom_fix_runtime_permitted());
    reset(); enable = "01"; assert(!zoom_fix_runtime_permitted());
    reset(); current_pid = 2200; assert(!zoom_fix_runtime_permitted());
    pid_text = "2200"; assert(zoom_fix_runtime_permitted());
    zoom_fix_latch_fault(3); zoom_fix_latch_fault(4);
    assert(!zoom_fix_runtime_permitted() && zoom_fix_state.first_fault == 3);
    reset(); zoom_fix_state.versions_verified = 0;
    assert(!zoom_fix_runtime_permitted() && zoom_fix_state.first_fault == FAULT_VERSION);
    reset(); pthread_t a, b;
    assert(pthread_create(&a, 0, counter, (void *)(uptr)2) == 0);
    assert(pthread_create(&b, 0, counter, (void *)(uptr)ZOOM_FIX_TELE_ID) == 0);
    assert(pthread_join(a, 0) == 0 && pthread_join(b, 0) == 0);
    assert(zoom_fix_state.changed_id2 == 10000 && zoom_fix_state.changed_tele == 10000);
    /* The other rear ID is never this device's telephoto counter. */
    zoom_fix_note_changed(ZOOM_FIX_TELE_ID == 3 ? 4 : 3);
    assert(zoom_fix_state.changed_id2 == 10000 && zoom_fix_state.changed_tele == 10000);
    zoom_fix_latch_fault(3); zoom_fix_note_changed(2);
    assert(zoom_fix_state.changed_id2 == 10000);
    printf("PASS provider PID gate, sticky fault and concurrent counters for telephoto ID %d\n", ZOOM_FIX_TELE_ID);
    return 0;
}
