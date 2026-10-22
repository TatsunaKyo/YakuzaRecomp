// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic movie-style REF/REFE scratchpad transfer; no original game data.
#include "runtime/ps2_memory.h"
#include "ps2_runtime.h"
#include "yakuza/native_device_error.h"
#include <iostream>
#include <stdexcept>

void check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
int main() {
    PS2Memory memory; check(memory.initialize(), "Memory initialization failed");
    constexpr uint32_t dma=0x1000d400, tag=0x10000, first=0x11000, second=0x12000;
    for (unsigned i=0;i<32;++i) memory.write8(first+i,uint8_t(0x40+i));
    for (unsigned i=0;i<16;++i) memory.write8(second+i,uint8_t(0x90+i));
    memory.write64(tag,(uint64_t(first)<<32)|(3u<<28)|2);
    memory.write64(tag+8,0xfeedfacecafebeefull);
    memory.write64(tag+16,(uint64_t(second)<<32)|1); // REFE.
    memory.write64(tag+24,0x1122334455667788ull);
    memory.write32(0x1000e000,1);
    memory.write32(dma+0x80,0x3ff0);
    memory.write32(dma+0x30,tag);
    memory.write32(dma+0x20,0);
    memory.write32(dma,0x105);
    for (unsigned i=0;i<48;++i) {
        const auto expected=uint8_t(i<32 ? 0x40+i : 0x90+i-32);
        check(memory.read8(0x70000000|((0x3ff0+i)&0x3fff))==expected,
              "Scratchpad source chain did not copy original payload bytes");
    }
    check(memory.read32(dma+0x20)==0,"Source-chain QWC did not finish");
    check(memory.read32(dma+0x10)==second+16,"Source-chain MADR differs");
    check(memory.read32(dma+0x30)==tag+32,"Source-chain TADR differs");
    check(memory.read32(dma+0x80)==0x20,"Scratchpad SADR did not wrap");
    check(!(memory.read32(dma)&0x100),"Completed source chain retained STR");
    check(memory.read32(0x1000e010)&(1u<<9),"Source-chain completion not signaled");
    // NEXT carries inline bytes, then jumps to an END tag with more bytes.
    memory.write64(tag,(uint64_t(tag+0x100)<<32)|(2u<<28)|1);
    memory.write64(tag+0x100,(7u<<28)|1);
    for(unsigned i=0;i<16;++i) {
        memory.write8(tag+16+i,uint8_t(i+3));memory.write8(tag+0x110+i,uint8_t(i+0xa0));
    }
    memory.write32(dma+0x80,0x100);memory.write32(dma+0x30,tag);memory.write32(dma,0x105);
    for(unsigned i=0;i<32;++i)
        check(memory.read8(0x70000100+i)==uint8_t(i<16 ? i+3 : i-16+0xa0),"NEXT/END payload differs");
    check(memory.read32(dma+0x30)==tag+0x120,"END TADR did not skip inline payload");
    // CNT follows its inline payload, including a zero-length terminal tag.
    memory.write64(tag,(1u<<28)|1);memory.write64(tag+32,7u<<28);
    memory.write32(dma+0x80,0x200);memory.write32(dma+0x30,tag);memory.write32(dma,0x105);
    check(memory.read8(0x70000200)==3,"CNT did not copy inline payload");
    check(memory.read32(dma+0x30)==tag+48,"Zero-length END did not terminate");
    // IRQ stops a TIE-enabled chain before an intentionally invalid next tag.
    memory.write64(tag,(uint64_t(first)<<32)|(3u<<28)|0x80000001u);
    memory.write32(dma+0x80,0x300);memory.write32(dma+0x30,tag);memory.write32(dma,0x185);
    check(memory.read8(0x70000300)==0x40,"TIE stopped before the IRQ payload");
    check(memory.read32(dma+0x30)==tag+16,"TIE failed to stop at the IRQ tag");
    // A tag and its inline source can also reside in scratchpad memory.
    memory.write64(0x70003fe0,(7u<<28)|1);
    for(unsigned i=0;i<16;++i) memory.write8(0x70003ff0+i,uint8_t(0x60+i));
    memory.write32(dma+0x80,0x400);memory.write32(dma+0x30,0x80003fe0);memory.write32(dma,0x105);
    for(unsigned i=0;i<16;++i) check(memory.read8(0x70000400+i)==0x60+i,"SPR tag/source differs");
    check(memory.read32(dma+0x30)==0x80000000,"SPR inline tag address did not wrap");
    // Invalid sources must not copy a block or signal successful completion.
    memory.write32(0x1000e010,1u<<9);
    memory.write64(tag,(uint64_t(0x2000000)<<32)|1);
    memory.write32(dma+0x80,0x400);memory.write32(dma+0x30,tag);
    bool rejected=false;
    try { memory.write32(dma,0x105); } catch(const yakuza::NativeDeviceError&) { rejected=true; }
    check(rejected,"Out-of-bounds source chain was accepted");
    check(memory.read8(0x70000400)==0x60,"Invalid source overwrote scratchpad");
    check(!(memory.read32(0x1000e010)&(1u<<9)),"Invalid source signaled completion");
    memory.write32(dma,0);memory.write32(dma+0x20,0);
    // Unsupported tag behavior propagates through real runtime memory helpers.
    PS2Runtime runtime;check(runtime.memory().initialize(),"Runtime initialization failed");
    runtime.memory().write32(0x1000e000,1);runtime.memory().write64(tag,5u<<28);
    runtime.memory().write32(dma+0x30,tag);R5900Context context{};context.pc=0x100008;
    rejected=false;
    try { runtime.Store32(runtime.memory().getRDRAM(),&context,dma,0x105); }
    catch(const yakuza::NativeDeviceError&) { rejected=true; }
    check(rejected,"Runtime swallowed unsupported scratchpad DMA behavior");
    std::cout<<"Scratchpad chain bytes, wrap, tag modes, TIE, bounds and native errors pass\n";
}
