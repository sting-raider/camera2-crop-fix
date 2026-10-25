/* SPDX-License-Identifier: Apache-2.0
 * Runtime ABI validation, PID-bound enable gate and atomic fault state.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long u64;
typedef unsigned long uptr;
_Static_assert(sizeof(void *) == 8 && sizeof(u64) == 8, "AArch64 LP64 required");
/* Same per-device telephoto camera ID as guard.c, from tools/build.py. */
#ifndef ZOOM_FIX_TELE_ID
#error "Build with -DZOOM_FIX_TELE_ID=<telephoto camera ID>"
#endif

extern void zoom_fix_entry(void) __attribute__((visibility("hidden")));
extern int zoom_guarded_c_wrapper(void *, void *, u32, u32, const void *)
    __attribute__((visibility("hidden")));
extern int zoom_fix_property_get(const char *, char *);
extern int zoom_fix_getpid(void);

typedef struct {
    _Atomic(u32) first_fault;
    _Atomic(u32) versions_verified;
    _Atomic(u32) changed_id2;
    _Atomic(u32) changed_tele;
    u8 reserved[48];
} FixState;
_Static_assert(sizeof(FixState) == 64, "reviewed state size");
#ifdef ZOOM_FIX_PROVIDER_HOST_TEST
__attribute__((aligned(64)))
#else
__attribute__((section(".zoom_fix.bss"), aligned(64), visibility("hidden")))
#endif
FixState zoom_fix_state;

enum { FAULT_VERSION = 100 };
static const u8 server_id[16] = {0x07,0x4a,0x3f,0xab,0x41,0x15,0x2e,0x63,0x9e,0x13,0xe3,0xf1,0xaa,0xe4,0x72,0x25};
static const u8 client_id[16] = {0xa2,0xad,0x72,0x6b,0xce,0x48,0x5f,0x73,0xc2,0xca,0xc7,0x3c,0xa7,0x69,0xea,0x72};
static const u8 metadata_id[16] = {0xe0,0xe6,0x8c,0x54,0x07,0x16,0x95,0x35,0x3e,0x92,0x1f,0xef,0xf3,0x9a,0xb9,0x12};
static const u8 send_prefix[32] = {0xff,0x83,0x07,0xd1,0xfd,0x7b,0x18,0xa9,0xfc,0x6f,0x19,0xa9,0xfa,0x67,0x1a,0xa9,0xf8,0x5f,0x1b,0xa9,0xf6,0x57,0x1c,0xa9,0xf4,0x4f,0x1d,0xa9,0xfd,0x03,0x06,0x91};
static const u8 mapper_prefix[32] = {0xff,0x43,0x02,0xd1,0xfd,0x7b,0x04,0xa9,0xf9,0x2b,0x00,0xf9,0xf8,0x5f,0x06,0xa9,0xf6,0x57,0x07,0xa9,0xf4,0x4f,0x08,0xa9,0xfd,0x03,0x01,0x91,0x57,0xd0,0x3b,0xd5};
static const u8 lock_prefix[20] = {0xe8,0x03,0x00,0xaa,0x00,0x04,0x40,0xf9,0x29,0x00,0x80,0x52,0x09,0x41,0x00,0x39,0xc0,0x03,0x5f,0xd6};
static const u8 update_prefix[32] = {0xfd,0x7b,0xbc,0xa9,0xf7,0x0b,0x00,0xf9,0xf6,0x57,0x02,0xa9,0xf4,0x4f,0x03,0xa9,0xfd,0x03,0x00,0x91,0x08,0x40,0x40,0x39,0x1f,0x05,0x00,0x71,0xe1,0x01,0x00,0x54};
static const u8 find_prefix[4] = {0x06,0x04,0x00,0x14};

static int bytes_equal(const u8 *a, const u8 *b, u32 count) {
    for (u32 index = 0; index < count; ++index) if (a[index] != b[index]) return 0;
    return 1;
}
static u16 read16(const u8 *base, u64 offset) { return *(const u16 *)(base + offset); }
static u32 read32(const u8 *base, u64 offset) { return *(const u32 *)(base + offset); }
static u64 read64(const u8 *base, u64 offset) { return *(const u64 *)(base + offset); }

static const u8 *self_base(void) {
#ifdef ZOOM_FIX_PROVIDER_HOST_TEST
    extern const u8 *zoom_test_image_base(void);
    return zoom_test_image_base();
#else
    return (const u8 *)((uptr)&zoom_fix_entry - 0x391900);
#endif
}

/* Bounded ELF GNU BuildID walk over PT_NOTE segments.
 * The input bases come from this image and its eagerly-resolved original GOT.
 * It does not attempt signal-catching for arbitrary corrupt native pointers.
 */
static int image_id(const u8 *base, u64 limit, const u8 expected[16]) {
    if ((uptr)base == 0 || ((uptr)base & 0xfff) != 0 ||
        read32(base, 0) != 0x464c457f || base[4] != 2 || base[5] != 1 ||
        read16(base, 16) != 3 || read16(base, 18) != 183) return 0;
    u64 phoff = read64(base, 0x20);
    u32 phsize = read16(base, 0x36), phnum = read16(base, 0x38);
    if (phoff > 0x10000 || phsize != 56 || phnum == 0 || phnum > 128 ||
        phoff + (u64)phsize * phnum > limit) return 0;
    for (u32 index = 0; index < phnum; ++index) {
        const u8 *ph = base + phoff + (u64)index * phsize;
        if (read32(ph, 0) != 4) continue;
        u64 vaddr = read64(ph, 16), size = read64(ph, 32);
        if (vaddr > limit || size > 0x10000 || size > limit - vaddr) return 0;
        u64 position = 0;
        while (position + 12 <= size) {
            const u8 *note = base + vaddr + position;
            u32 namesize = read32(note, 0), descsize = read32(note, 4), type = read32(note, 8);
            if (namesize > 128 || descsize > 128) break;
            u64 aligned_name = ((u64)namesize + 3) & ~(u64)3;
            u64 aligned_desc = ((u64)descsize + 3) & ~(u64)3;
            u64 next = position + 12 + aligned_name + aligned_desc;
            if (next <= position || next > size) break;
            if (type == 3 && namesize == 4 && read32(note, 12) == 0x00554e47)
                return descsize == 16 && bytes_equal(note + 12 + aligned_name, expected, 16);
            position = next;
        }
    }
    return 0;
}

static int plt_equal(const u8 *base, u64 offset, u32 a, u32 b, u32 c) {
    return read32(base, offset) == a && read32(base, offset + 4) == b &&
        read32(base, offset + 8) == c && read32(base, offset + 12) == 0xd61f0220;
}
static int versions_match(void) {
    const u8 *base = self_base();
    if (!image_id(base, 0x3cc000, server_id) ||
        !bytes_equal(base + 0x257bfc, send_prefix, 32) ||
        !bytes_equal(base + 0x372ff4, mapper_prefix, 32)) return 0;
    /* Exact direct primary BL to the new file-backed entry; subresult BL stays
     * original and is checked too. This is a patched-callsite compatibility
     * check, not a claim that the old GNU note identifies the new payload. */
    if (read32(base, 0x2581fc) != (0x94000000U | ((0x391900U - 0x2581fcU) >> 2)) ||
        read32(base, 0x258684) != 0x94046a5c ||
        read32(base, 0x391900) != 0xaa1503e4) return 0;
#ifndef ZOOM_FIX_PROVIDER_HOST_TEST
    u32 tail = read32(base, 0x391904);
    int displacement = (int)(tail << 6) >> 4;
    if ((tail & 0xfc000000) != 0x14000000 ||
        (uptr)(base + 0x391904) + displacement != (uptr)&zoom_guarded_c_wrapper) return 0;
#endif
    if (!plt_equal(base, 0x3901c0, 0xd00001b0, 0xf9474a11, 0x913a4210) ||
        !plt_equal(base, 0x38df30, 0x900001d0, 0xf946a611, 0x91352210) ||
        !plt_equal(base, 0x38f510, 0xf00001b0, 0xf9441e11, 0x9120e210) ||
        !plt_equal(base, 0x391880, 0xd00001b0, 0xf944fa11, 0x9127c210) ||
        !plt_equal(base, 0x38dda0, 0x900001d0, 0xf9464211, 0x91320210)) return 0;
    uptr find = (uptr)read64(base, 0x3c6e90);
    uptr update = (uptr)read64(base, 0x3c5d48);
    uptr lock = (uptr)read64(base, 0x3c6838);
    if (find < 0xd2d8 || update < 0x68294 || lock < 0x67de4 ||
        (find & 3) || (update & 3) || (lock & 3) || update - 0x68294 != lock - 0x67de4) return 0;
    const u8 *metadata = (const u8 *)(find - 0xd2d8);
    const u8 *client = (const u8 *)(update - 0x68294);
    return image_id(metadata, 0x18000, metadata_id) && image_id(client, 0xa0000, client_id) &&
        bytes_equal(metadata + 0xd2d8, find_prefix, 4) &&
        bytes_equal(client + 0x68294, update_prefix, 32) &&
        bytes_equal(client + 0x67de4, lock_prefix, 20);
}

void zoom_fix_latch_fault(u32 reason) {
    if (!reason) reason = FAULT_VERSION;
    u32 expected = 0;
    __atomic_compare_exchange_n((u32 *)&zoom_fix_state.first_fault, &expected, reason,
        0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
}
void zoom_fix_note_changed(u32 id) {
    if (__atomic_load_n((u32 *)&zoom_fix_state.first_fault, __ATOMIC_ACQUIRE) ||
        __atomic_load_n((u32 *)&zoom_fix_state.versions_verified, __ATOMIC_ACQUIRE) != 1) return;
    if (id == 2) __atomic_fetch_add((u32 *)&zoom_fix_state.changed_id2, 1, __ATOMIC_RELAXED);
    else if (id == ZOOM_FIX_TELE_ID) __atomic_fetch_add((u32 *)&zoom_fix_state.changed_tele, 1, __ATOMIC_RELAXED);
}
static int authorized_pid(void) {
    char value[92];
    value[0] = value[91] = 0;
    int length = zoom_fix_property_get("persist.camera.zoom_crop_fix.pid", value);
    if (length < 1 || length > 10 || value[0] < '1' || value[0] > '9' || value[length] != 0) return 0;
    u32 parsed = 0;
    for (int index = 0; index < length; ++index) {
        if (value[index] < '0' || value[index] > '9') return 0;
        u32 digit = (u32)(value[index] - '0');
        if (parsed > (2147483647U - digit) / 10U) return 0;
        parsed = parsed * 10U + digit;
    }
    int actual = zoom_fix_getpid();
    return actual > 0 && parsed == (u32)actual;
}
int zoom_fix_runtime_permitted(void) {
    if (__atomic_load_n((u32 *)&zoom_fix_state.first_fault, __ATOMIC_ACQUIRE)) return 0;
    if (__atomic_load_n((u32 *)&zoom_fix_state.versions_verified, __ATOMIC_ACQUIRE) != 1) {
        /* Read-only checks may run concurrently, so no other callback has to
         * skip a qualifying first frame while one thread verifies the image. */
        if (!versions_match()) { zoom_fix_latch_fault(FAULT_VERSION); return 0; }
        __atomic_store_n((u32 *)&zoom_fix_state.versions_verified, 1, __ATOMIC_RELEASE);
    }
    char value[92];
    value[0] = value[91] = 0;
    if (zoom_fix_property_get("persist.camera.zoom_crop_fix", value) != 1 ||
        value[0] != '1' || value[1] != 0) return 0;
    return authorized_pid() &&
        __atomic_load_n((u32 *)&zoom_fix_state.first_fault, __ATOMIC_ACQUIRE) == 0;
}
