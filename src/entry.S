/* SPDX-License-Identifier: Apache-2.0 */
/* Entry reached only by a replacement direct BL at primary 0x2581fc.
 * x21 holds CaptureOutputStates from sendCaptureResult prologue 0x257c40.
 * Tail branch preserves original LR=base+0x258200 and all callee-saved state.
 */
.text
.p2align 2
.global zoom_primary_entry
.global zoom_fix_entry
.hidden zoom_primary_entry
.hidden zoom_fix_entry
.type zoom_primary_entry, %function
.type zoom_fix_entry, %function
zoom_fix_entry:
zoom_primary_entry:
    mov x4, x21
    b zoom_guarded_c_wrapper
.size zoom_primary_entry, .-zoom_primary_entry
.size zoom_fix_entry, .-zoom_fix_entry
.section .note.GNU-stack,"",%progbits
