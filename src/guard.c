/* SPDX-License-Identifier: Apache-2.0
 * Guarded physical-rear Camera2 crop metadata correction.
 */
typedef unsigned char u8;
typedef unsigned int u32;
typedef signed int i32;
typedef unsigned long usize;
typedef signed long i64;
typedef unsigned long uptr;
_Static_assert(sizeof(void *) == 8 && sizeof(usize) == 8, "ELF64 ABI required");

typedef struct {
    usize index;
    u32 tag;
    u8 type;
    u8 reserved[3];
    usize count;
    const void *data;
} RoEntry;
_Static_assert(sizeof(RoEntry) == 32, "camera_metadata_ro_entry_t size");
_Static_assert(__builtin_offsetof(RoEntry, tag) == 8, "entry tag offset");
_Static_assert(__builtin_offsetof(RoEntry, type) == 12, "entry type offset");
_Static_assert(__builtin_offsetof(RoEntry, count) == 16, "entry count offset");
_Static_assert(__builtin_offsetof(RoEntry, data) == 24, "entry data offset");

/* Fixed-VA direct relocations, not indirect calls or new dynamic imports.
 * original_mapper -> cameraserver 0x372ff4
 * find_ro_entry   -> existing C PLT 0x3901c0
 * update_i32      -> existing C++ int32 update PLT 0x38df30, explicit this.
 * The C++ const CameraMetadata::find PLT at 0x38ed30 is NOT used: it has x8 sret.
 */
extern int zoom_fix_original_mapper(void *, void *, u32, u32);
extern int zoom_fix_find_ro_entry(const void *, u32, RoEntry *);
extern int zoom_fix_update_i32(void *, u32, const i32 *, usize);
extern int zoom_fix_runtime_permitted(void);
extern void zoom_fix_latch_fault(u32);
extern void zoom_fix_note_changed(u32);

enum {
    ZOOM = 0x1002f, CROP = 0xd0000, FOCAL = 0x80002,
    PIXEL = 0xe0020, PHYSICAL = 0x1a0002, DISTORTION = 0x1b0000,
    INTENT = 0x1000d, OVERRIDE = 0x10034, AUTOFRAMING = 0x10037,
    TIMESTAMP = 0xe0010, EIS = 0x10011, OIS = 0x80004,
    ACTIVE = 0xf0000, PRE_ACTIVE = 0xf000a,
};
enum { FAULT_READ = 1, FAULT_UPDATE = 2, FAULT_MAPPER = 3, FAULT_AFTER_READ = 4 };

static const void *ptr_at(const void *p, usize offset) {
    return *(const void *const *)((const u8 *)p + offset);
}
static i32 i32_at(const void *p, usize offset) {
    return *(const i32 *)((const u8 *)p + offset);
}
static double absolute(double value) { return value < 0.0 ? -value : value; }
static double maximum(double a, double b) { return a > b ? a : b; }

/* Return -1 malformed/API error, 0 absent, 1 present. Data is read only after
 * tag/type/count/null checks. RequiredCount=-1 permits any count up to 32.
 */
static int entry(const void *raw, u32 tag, u8 type, int required_count, RoEntry *out) {
    RoEntry value = {0};
    int status = zoom_fix_find_ro_entry(raw, tag, &value);
    if (status == -2) return 0;
    if (status != 0 || value.tag != tag || value.type != type || value.count > 32 ||
        (required_count >= 0 && value.count != (usize)required_count) ||
        (value.count != 0 && value.data == (const void *)0)) return -1;
    *out = value;
    return 1;
}

typedef struct {
    double zoom, focal;
    i32 crop[4], override_value;
    u8 pixel, intent, eis, autoframing;
    u8 has_zoom, has_focal, has_crop, has_pixel, has_intent, has_eis;
    u8 has_override, has_autoframing, physical_nonempty, locked;
} Snapshot;

static int snapshot(const void *metadata, Snapshot *out) {
    if (metadata == (const void *)0) return -1;
    const void *raw = ptr_at(metadata, 8);
    if (raw == (const void *)0) return -1;
    Snapshot value = {0};
    RoEntry found;
    int present;
#define READ_SCALAR(TAG, TYPE, FIELD, HAS, CTYPE) do { \
    present = entry(raw, TAG, TYPE, 1, &found); \
    if (present < 0) return -1; \
    value.HAS = (u8)present; \
    if (present) value.FIELD = *(const CTYPE *)found.data; \
} while (0)
    READ_SCALAR(ZOOM, 2, zoom, has_zoom, float);
    READ_SCALAR(FOCAL, 2, focal, has_focal, float);
    READ_SCALAR(PIXEL, 0, pixel, has_pixel, u8);
    READ_SCALAR(INTENT, 0, intent, has_intent, u8);
    READ_SCALAR(EIS, 0, eis, has_eis, u8);
    READ_SCALAR(OVERRIDE, 1, override_value, has_override, i32);
    READ_SCALAR(AUTOFRAMING, 0, autoframing, has_autoframing, u8);
#undef READ_SCALAR
    present = entry(raw, CROP, 1, 4, &found);
    if (present < 0) return -1;
    value.has_crop = (u8)present;
    if (present) for (u32 index = 0; index < 4; ++index) value.crop[index] = ((const i32 *)found.data)[index];
    present = entry(raw, PHYSICAL, 0, -1, &found);
    if (present < 0) return -1;
    value.physical_nonempty = (u8)(present && found.count != 0);
    /* These three tags are observational in JS, but malformed type/count is
     * still a JS snapshot error. Retain those rejection checks here too. */
    if (entry(raw, TIMESTAMP, 3, 1, &found) < 0 ||
        entry(raw, DISTORTION, 0, 1, &found) < 0 ||
        entry(raw, OIS, 0, 1, &found) < 0) return -1;
    value.locked = *((const u8 *)metadata + 16);
    *out = value;
    return 0;
}

/* CaptureOutputStates.cameraId is a const libc++ string reference at +0.
 * Only exact one-character IDs 2/4 (OnePlus 15 main/tele) can qualify, so reject other valid strings
 * before further reads. Both verified short and long layouts are supported. */
static u32 source_id(const void *states) {
    if (states == (const void *)0) return 0;
    const u8 *string = ptr_at(states, 0);
    if (string == (const u8 *)0) return 0;
    usize count = (string[0] & 1) ? *(const usize *)(string + 8) : string[0] >> 1;
    if (count != 1) return 0;
    const u8 *data = (string[0] & 1) ? ptr_at(string, 16) : string + 1;
    if (data == (const u8 *)0 || data[1] != 0) return 0;
    return data[0] == '2' ? 2 : data[0] == '4' ? 3 : 0; /* tele keeps internal slot 3 */
}

static int arrays_match(const void *states) {
    const void *metadata = ptr_at(states, 0x98);
    if (metadata == (const void *)0) return 0;
    const void *raw = ptr_at(metadata, 8);
    if (raw == (const void *)0) return 0;
    const u32 tags[2] = { ACTIVE, PRE_ACTIVE };
    for (u32 index = 0; index < 2; ++index) {
        RoEntry found;
        if (entry(raw, tags[index], 1, 4, &found) != 1) return 0;
        const i32 *array = found.data;
        if (array[0] != 0 || array[1] != 0 || array[2] != 4096 || array[3] != 3072) return 0;
    }
    return 1;
}

static i32 rounded_bound(double value, i32 upper) {
    if (value <= 0.0) return 0;
    if (value >= (double)upper) return upper;
    /* Here value is nonnegative: trunc(value + .5) == JS Math.round(value).
     * No libm call or float approximation of the JS double geometry is used. */
    return (i32)(value + 0.5);
}

static int candidate(const void *mapper, const void *states, u32 id,
                     const Snapshot *raw, i32 corrected[4]) {
    if (mapper == (const void *)0 || !arrays_match(states) ||
        *((const u8 *)mapper + 0x20) != 1 || *((const u8 *)mapper + 0x34) != 1 ||
        i32_at(mapper, 0x24) != 4096 || i32_at(mapper, 0x28) != 3072 ||
        raw->locked != 0 || !raw->has_pixel || raw->pixel != 0 ||
        /* BSG9.6 uses CUSTOM(0) for its observed physical JPEG still request. */
        !raw->has_intent || (raw->intent != 0 && raw->intent != 1 && raw->intent != 2 && raw->intent != 5) ||
        !raw->has_eis || raw->eis != 0 || !raw->has_focal || !__builtin_isfinite(raw->focal) ||
        absolute(raw->focal - (id == 2 ? 5.59 : 12.19)) > 0.01 ||
        raw->physical_nonempty || (raw->has_override && raw->override_value != 0) ||
        (raw->has_autoframing && raw->autoframing != 0) || !raw->has_zoom ||
        !__builtin_isfinite(raw->zoom) || raw->zoom <= 1.01 ||
        /* Deliberate bound-only expansion from the original JS's 10.01:
         * even integer crop10 is 408x306, whose native float zoom is 4096/408.
         * The immediately larger float32 remains outside the accepted range. */
        raw->zoom > (double)(float)(4096.0 / 408.0) ||
        !raw->has_crop) return 0;
    i32 left = raw->crop[0], top = raw->crop[1];
    i32 width = raw->crop[2], height = raw->crop[3];
    if (width <= 0 || height <= 0 || left < 0 || top < 0 ||
        (i64)left + width > 4096 || (i64)top + height > 3072) return 0;
    double expected_w = 4096.0 / raw->zoom, expected_h = 3072.0 / raw->zoom;
    if (absolute(width - expected_w) > maximum(16.0, expected_w * 0.05) ||
        absolute(height - expected_h) > maximum(16.0, expected_h * 0.05) ||
        absolute(left + width / 2.0 - 2048.0) > 16.0 ||
        absolute(top + height / 2.0 - 1536.0) > 16.0) return 0;
    i32 new_left = rounded_bound(2048.0 + raw->zoom * (left - 2048.0), 4096);
    i32 new_top = rounded_bound(1536.0 + raw->zoom * (top - 1536.0), 3072);
    i32 right = rounded_bound(2048.0 + raw->zoom * (left + (double)width - 2048.0), 4096);
    i32 bottom = rounded_bound(1536.0 + raw->zoom * (top + (double)height - 1536.0), 3072);
    corrected[0] = new_left;
    corrected[1] = new_top;
    corrected[2] = right - new_left;
    corrected[3] = bottom - new_top;
    return corrected[2] > 0 && corrected[3] > 0;
}

int zoom_guarded_c_wrapper(void *mapper, void *metadata, u32 method_is_ratio,
                           u32 ratio_is_one, const void *states) {
    if (!zoom_fix_runtime_permitted())
        return zoom_fix_original_mapper(mapper, metadata, method_is_ratio, ratio_is_one);
    u32 id = source_id(states);
    if (!id) return zoom_fix_original_mapper(mapper, metadata, method_is_ratio, ratio_is_one);
    Snapshot before;
    i32 corrected[4];
    int changed = 0;
    if (snapshot(metadata, &before) != 0) {
        zoom_fix_latch_fault(FAULT_READ);
    } else if (candidate(mapper, states, id, &before, corrected)) {
        if (zoom_fix_update_i32(metadata, CROP, corrected, 4) != 0)
            zoom_fix_latch_fault(FAULT_UPDATE);
        else
            changed = 1;
    }
    /* Original mapping always runs once, with exactly the original arguments. */
    int status = zoom_fix_original_mapper(mapper, metadata, method_is_ratio, ratio_is_one);
    if (status != 0) {
        zoom_fix_latch_fault(FAULT_MAPPER);
    } else {
        Snapshot after;
        if (snapshot(metadata, &after) != 0)
            zoom_fix_latch_fault(FAULT_AFTER_READ);
        else if (changed)
            zoom_fix_note_changed(id);
    }
    return status;
}
