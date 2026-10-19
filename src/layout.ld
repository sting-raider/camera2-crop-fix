/* SPDX-License-Identifier: Apache-2.0 */
/* Link only the new code and state; retain the original image headers. */
ENTRY(zoom_fix_entry)
SECTIONS {
  . = 0x391900;
  .zoom_fix.text : { KEEP(*entry.o(.text*)) *(.text*) }
  .zoom_fix.rodata : { *(.rodata*) }
  ASSERT(. <= 0x394000, "Code/constants exceed reviewed RX zero gap")
  .zoom_fix.unexpected : { *(.data*) *(.got*) *(.plt*) }
  ASSERT(SIZEOF(.zoom_fix.unexpected) == 0, "Unexpected initialized writable or dynamic content")
  .zoom_fix.rela : { *(.rela*) }
  .zoom_fix.rel : { *(.rel.*) }
  .zoom_fix.dynamic : { *(.dynamic*) }
  .zoom_fix.dynsym : { *(.dynsym*) }
  .zoom_fix.dynstr : { *(.dynstr*) }
  .zoom_fix.interp : { *(.interp*) }
  ASSERT(SIZEOF(.zoom_fix.rela) == 0 && SIZEOF(.zoom_fix.rel) == 0 && SIZEOF(.zoom_fix.dynamic) == 0 && SIZEOF(.zoom_fix.dynsym) == 0 && SIZEOF(.zoom_fix.dynstr) == 0 && SIZEOF(.zoom_fix.interp) == 0, "Dynamic content is forbidden")
  . = 0x3ca040;
  .zoom_fix.bss (NOLOAD) : { *(.zoom_fix.bss) *(.bss*) *(COMMON) }
  ASSERT(ADDR(.zoom_fix.bss) == 0x3ca040, "State moved from reviewed RW address")
  ASSERT(SIZEOF(.zoom_fix.bss) <= 256, "State exceeds reviewed 256-byte bound")
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.llvm_addrsig) }
}
zoom_fix_original_mapper = 0x372ff4;
zoom_fix_find_ro_entry = 0x3901c0;
zoom_fix_update_i32 = 0x38df30;
zoom_fix_property_get = 0x391880;
zoom_fix_getpid = 0x38dda0;
