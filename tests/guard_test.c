/* SPDX-License-Identifier: Apache-2.0
 * Host-only integration harness. No Android binary, camera, or device API. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../src/guard.c"

typedef struct { u32 lookup; RoEntry value; } Item;
typedef struct { Item items[20]; usize size; } Raw;
typedef struct { uptr vtable; Raw *raw; u8 locked; } Metadata;
static _Alignas(8) u8 states[0xa0], string_value[24], mapper_value[64];
static Raw raw_result, raw_static;
static Metadata metadata_result, metadata_static;
static float zoom_value, focal_value;
static u8 pixel_value, intent_value, eis_value, flag_value;
static i32 crop_value[4], array_active[4], array_pre[4], override_value;
static i64 timestamp_value[2];
static int permitted, fault_code, changes, original_calls, update_calls, original_status, update_status, corrupt_after;
static void *expected_mapper, *expected_metadata;
static u32 expected_method, expected_ratio;

static void add(Raw *raw, u32 tag, u8 type, usize count, const void *data) {
    raw->items[raw->size++] = (Item){tag, {0, tag, type, {0}, count, data}};
}
static Item *item(Raw *raw, u32 tag) {
    for (usize i = 0; i < raw->size; ++i) if (raw->items[i].lookup == tag) return &raw->items[i];
    return 0;
}
int zoom_fix_runtime_permitted(void) { return permitted && !fault_code; }
void zoom_fix_latch_fault(u32 why) { if (!fault_code) fault_code = (int)why; }
void zoom_fix_note_changed(u32 id) { assert(id == 2 || id == 3); ++changes; }
int zoom_fix_find_ro_entry(const void *buffer, u32 tag, RoEntry *out) {
    Item *found = item((Raw *)buffer, tag);
    if (!found) return -2;
    *out = found->value;
    return 0;
}
int zoom_fix_update_i32(void *metadata, u32 tag, const i32 *data, usize count) {
    assert(metadata == expected_metadata && tag == CROP && count == 4);
    ++update_calls;
    if (!update_status) memcpy(crop_value, data, 16);
    return update_status;
}
int zoom_fix_original_mapper(void *mapper, void *metadata, u32 method, u32 ratio) {
    assert(mapper == expected_mapper && metadata == expected_metadata);
    assert(method == expected_method && ratio == expected_ratio);
    ++original_calls;
    if (corrupt_after) item(&raw_result, EIS)->value.type = 1;
    return original_status;
}

static void reset(void) {
    memset(states, 0, sizeof(states)); memset(string_value, 0, sizeof(string_value));
    memset(mapper_value, 0, sizeof(mapper_value)); memset(&raw_result, 0, sizeof(raw_result));
    memset(&raw_static, 0, sizeof(raw_static));
    permitted = 1; fault_code = changes = original_calls = update_calls = 0;
    original_status = update_status = corrupt_after = 0;
    zoom_value = 2.0f; focal_value = 5.59f; pixel_value = 0; intent_value = 1; eis_value = 0;
    flag_value = 1; override_value = 0;
    i32 crop[4] = {1024,768,2048,1536}, array[4] = {0,0,4096,3072};
    memcpy(crop_value, crop, 16); memcpy(array_active, array, 16); memcpy(array_pre, array, 16);
    metadata_result = (Metadata){0, &raw_result, 0};
    metadata_static = (Metadata){0, &raw_static, 0};
    string_value[0] = 2; string_value[1] = '2';
    *(const void **)states = string_value;
    *(const void **)(states + 0x98) = &metadata_static;
    mapper_value[0x20] = mapper_value[0x34] = 1;
    *(i32 *)(mapper_value + 0x24) = 4096; *(i32 *)(mapper_value + 0x28) = 3072;
    add(&raw_result, ZOOM, 2, 1, &zoom_value); add(&raw_result, FOCAL, 2, 1, &focal_value);
    add(&raw_result, PIXEL, 0, 1, &pixel_value); add(&raw_result, INTENT, 0, 1, &intent_value);
    add(&raw_result, EIS, 0, 1, &eis_value); add(&raw_result, CROP, 1, 4, crop_value);
    add(&raw_static, ACTIVE, 1, 4, array_active); add(&raw_static, PRE_ACTIVE, 1, 4, array_pre);
    expected_mapper = mapper_value; expected_metadata = &metadata_result;
    expected_method = 0; expected_ratio = 1;
}
static int run(void) {
    int result = zoom_guarded_c_wrapper(expected_mapper, expected_metadata, expected_method, expected_ratio, states);
    assert(original_calls == 1);
    return result;
}
static void unchanged(void) { assert(run() == 0 && update_calls == 0 && changes == 0 && !fault_code); }
static void legacy10(float ratio, u8 id) {
    reset(); zoom_value = ratio; string_value[1] = id;
    focal_value = id == '2' ? 5.59f : 12.19f;
    crop_value[0] = 1844; crop_value[1] = 1383; crop_value[2] = 408; crop_value[3] = 306;
}

int main(void) {
    int cases = 0;
    reset(); assert(run() == 0 && update_calls == 1 && changes == 1 && !fault_code);
    assert(crop_value[0] == 0 && crop_value[1] == 0 && crop_value[2] == 4096 && crop_value[3] == 3072); ++cases;
    reset(); string_value[1] = '4'; focal_value = 12.19f; zoom_value = 10.0f;
    crop_value[0] = 1843; crop_value[1] = 1382; crop_value[2] = 410; crop_value[3] = 308;
    assert(run() == 0 && update_calls == 1 && changes == 1);
    assert(crop_value[0] == 0 && crop_value[1] == 0 && crop_value[2] == 4096 && crop_value[3] == 3072); ++cases;
    reset(); string_value[1] = '0'; unchanged(); ++cases;
    reset(); eis_value = 1; unchanged(); ++cases;
    reset(); metadata_result.locked = 1; unchanged(); ++cases;
    reset(); array_pre[0] = 1; unchanged(); ++cases;
    reset(); item(&raw_result, PIXEL)->lookup = 0xffffffffU; unchanged(); ++cases;
    reset(); add(&raw_result, PHYSICAL, 0, 1, &flag_value); unchanged(); ++cases;
    reset(); override_value = 1; add(&raw_result, OVERRIDE, 1, 1, &override_value); unchanged(); ++cases;
    reset(); add(&raw_result, AUTOFRAMING, 0, 1, &flag_value); unchanged(); ++cases;
    reset(); intent_value = 3; unchanged(); ++cases;
    reset(); zoom_value = __builtin_inff(); unchanged(); ++cases;
    reset(); crop_value[0] += 17; unchanged(); ++cases;
    reset(); crop_value[0] = crop_value[1] = 0; crop_value[2] = 4096; crop_value[3] = 3072; unchanged(); ++cases;
    reset(); item(&raw_result, FOCAL)->value.type = 1; assert(run() == 0 && fault_code == FAULT_READ && !update_calls); ++cases;
    reset(); add(&raw_result, TIMESTAMP, 3, 2, timestamp_value); assert(run() == 0 && fault_code == FAULT_READ && !update_calls); ++cases;
    reset(); item(&raw_result, CROP)->value.data = 0; assert(run() == 0 && fault_code == FAULT_READ && !update_calls); ++cases;
    reset(); update_status = -12; assert(run() == 0 && fault_code == FAULT_UPDATE && update_calls == 1 && changes == 0); ++cases;
    reset(); original_status = -22; assert(run() == -22 && fault_code == FAULT_MAPPER && changes == 0); ++cases;
    reset(); corrupt_after = 1; assert(run() == 0 && fault_code == FAULT_AFTER_READ && changes == 0); ++cases;
    reset(); permitted = 0; unchanged(); ++cases;
    reset(); static const char long_id[] = "2"; string_value[0] = 1;
    *(usize *)(string_value + 8) = 1; *(const void **)(string_value + 16) = long_id;
    assert(run() == 0 && changes == 1 && !fault_code); ++cases;
    reset(); expected_method = 1; expected_ratio = 0; assert(run() == 0 && changes == 1); ++cases;
    /* Recorded native legacy10=10.03921604 is beyond old JS 10.01. These
     * acceptance cases include quantized 10× crop requests. */
    float quantized_max = (float)(4096.0 / 408.0), below, above;
    u32 bits; memcpy(&bits, &quantized_max, 4);
    u32 adjacent = bits - 1; memcpy(&below, &adjacent, 4);
    adjacent = bits + 1; memcpy(&above, &adjacent, 4);
    assert(below < quantized_max && above > quantized_max);
    legacy10(10.0f, '2'); assert(run() == 0 && changes == 1);
    assert(crop_value[0] == 8 && crop_value[1] == 6 && crop_value[2] == 4080 && crop_value[3] == 3060); ++cases;
    legacy10(quantized_max, '2'); assert(run() == 0 && changes == 1 && !fault_code);
    assert(crop_value[0] == 0 && crop_value[1] == 0 && crop_value[2] == 4096 && crop_value[3] == 3072); ++cases;
    legacy10(quantized_max, '4'); assert(run() == 0 && changes == 1 && !fault_code);
    assert(crop_value[0] == 0 && crop_value[1] == 0 && crop_value[2] == 4096 && crop_value[3] == 3072); ++cases;
    legacy10(below, '2'); assert(run() == 0 && changes == 1 && !fault_code); ++cases;
    legacy10(above, '2'); unchanged(); ++cases;
    legacy10(10.04f, '2'); unchanged(); ++cases;
    legacy10(10.05f, '4'); unchanged(); ++cases;
    /* OnePlus 15 ID 3 is the 2.31 mm ultrawide; unverified, so never corrected. */
    reset(); string_value[1] = '3'; focal_value = 12.19f; unchanged(); ++cases;
    for (int id = '2'; id <= '4'; id += 2) {
        reset(); string_value[1] = (u8)id; focal_value = id == '2' ? 5.59f : 12.19f;
        intent_value = 0; assert(run() == 0 && changes == 1 && !fault_code); ++cases;
        legacy10(quantized_max, (u8)id); intent_value = 0;
        assert(run() == 0 && changes == 1 && !fault_code); ++cases;
    }
    for (int intent = 3; intent <= 7; ++intent) {
        if (intent == 5) continue;
        reset(); intent_value = (u8)intent; unchanged(); ++cases;
    }
    printf("PASS %d host integration cases; no device actions\n", cases);
    return 0;
}
