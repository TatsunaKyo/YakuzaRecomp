// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/scratchpad_dma.h"
#include "yakuza/native_device_error.h"
#include <algorithm>
#include <array>

namespace yakuza {
namespace {
constexpr uint32_t base=0x1000d400, spr=0x80000000u;
uint32_t advance(uint32_t address, uint32_t bytes) {
    return address&spr ? spr|((address+bytes)&0x3ff0) : address+bytes;
}
void validate(uint32_t address, uint32_t bytes, std::span<const uint8_t> ram) {
    if (address&spr) return;
    const uint32_t physical=address&0x1ffffff0;
    if (physical>ram.size() || bytes>ram.size()-physical)
        throw NativeDeviceError("Scratchpad DMA chain source is outside EE RAM");
}
std::array<uint8_t,16> readQuad(uint32_t address, std::span<const uint8_t> ram,
                              std::span<const uint8_t> scratch) {
    validate(address,16,ram);
    const auto source=address&spr ? scratch.subspan(address&0x3ff0,16) : ram.subspan(address&0x1ffffff0,16);
    std::array<uint8_t,16> quad;
    std::copy(source.begin(),source.end(),quad.begin()); return quad;
}
uint32_t word(const std::array<uint8_t,16>& quad, unsigned offset) {
    uint32_t value=0;
    for(unsigned i=0;i<4;++i) value|=uint32_t(quad[offset+i])<<(8*i);
    return value;
}
}
void runScratchpadSourceChain(uint32_t chcr, std::unordered_map<uint32_t,uint32_t>& io,
    std::span<const uint8_t> ram, std::span<const uint8_t> scratch, const ScratchpadWriter& write) {
    if (scratch.size()!=0x4000 || (chcr&0xd)!=5 || (chcr&0x40))
        throw NativeDeviceError("Unsupported scratchpad source-chain mode or tag transfer");
    uint32_t count=io[base+0x20]&0xffff, address=io[base+0x10]&~15u;
    uint32_t tag=io[base+0x30]&~15u, sadr=io[base+0x80]&0x3ff0;
    bool end=false;
    unsigned tags=0;
    while(true) {
        if (!count) {
            if (end) break;
            if (++tags>65536) throw NativeDeviceError("Scratchpad DMA chain exceeds tag budget");
            const auto data=readQuad(tag,ram,scratch);
            const uint32_t lo=word(data,0), pointer=word(data,4)&~15u;
            const unsigned id=(lo>>28)&7;
            count=lo&0xffff;
            const auto after=advance(tag,16);
            switch(id) {
            case 0: address=pointer; tag=after; end=true; break; // REFE.
            case 1: address=after; tag=advance(after,count*16); break; // CNT.
            case 2: address=after; tag=pointer; break; // NEXT.
            case 3: address=pointer; tag=after; break; // REF.
            case 7: address=after; tag=advance(after,count*16); end=true; break; // END.
            default: throw NativeDeviceError("Scratchpad DMA REFS/CALL/RET chains are not implemented");
            }
            end=end || ((chcr&0x80) && (lo&0x80000000u));
            chcr=(chcr&0xffff)|(lo&0xffff0000);
            io[base]=chcr; io[base+0x30]=tag;
            io[base+0x10]=address; io[base+0x20]=count;
        }
        validate(address,count*16,ram);
        while(count) {
            const auto quad=readQuad(address,ram,scratch);
            write(sadr,quad);
            address=advance(address,16); sadr=(sadr+16)&0x3ff0; --count;
            io[base+0x10]=address; io[base+0x20]=count; io[base+0x80]=sadr;
        }
    }
}
}
