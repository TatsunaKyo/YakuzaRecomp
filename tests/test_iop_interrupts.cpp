// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic IOP module: sound DMA must respect global/nested interrupt masking.
// IopHost fixture follows the pinned PS2Recomp emulator-test interface.
#include "ps2x/iop/iop_subsystem.h"
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace ps2x::iop;
class Host final : public IopHost {
public:
    std::vector<uint8_t> guest = std::vector<uint8_t>(4096);
    bool readGuest(uint32_t a, void* p, size_t n) const override {
        if (a > guest.size() || n > guest.size()-a) return false;
        if (n) std::memcpy(p, guest.data()+a, n);
        return true;
    }
    bool writeGuest(uint32_t a, const void* p, size_t n) override {
        if (a > guest.size() || n > guest.size()-a) return false;
        if (n) std::memcpy(guest.data()+a, p, n);
        return true;
    }
    bool zeroGuest(uint32_t a, size_t n) override {
        if (a > guest.size() || n > guest.size()-a) return false;
        if (n) std::memset(guest.data()+a, 0, n);
        return true;
    }
    bool normalizeGuestAddress(uint32_t a, uint32_t& out) const override { out=a; return a<=guest.size(); }
    uint32_t allocateIopHandle(IopHandleKind) override { return 1; }
    uint32_t allocateGuest(uint32_t,uint32_t) override { return 0; }
    void freeGuest(uint32_t) override {}
    void audioCommand(uint32_t,uint32_t,GuestBuffer,GuestBuffer) override {}
    std::string hostPath(HostPathKind) const override { return {}; }
    std::string translateGuestPath(std::string_view p) const override { return std::string(p); }
    uint64_t openHostFile(std::string_view) override { return 0; }
    bool hostFileSize(uint64_t,uint64_t&) const override { return false; }
    bool readHostFile(uint64_t,uint64_t,void*,size_t,size_t&) override { return false; }
    void closeHostFile(uint64_t) override {}
    int32_t memoryCard(const MemoryCardRequest&) override { return 0; }
    bool hasGuestFunction(uint32_t) const override { return false; }
    bool invokeGuestFunction(uint64_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t*) override { return false; }
    void log(LogLevel, std::string_view) override {}
};

void check(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
void put16(std::vector<uint8_t>& b, size_t o, uint16_t n) { b[o]=uint8_t(n); b[o+1]=uint8_t(n>>8); }
void put32(std::vector<uint8_t>& b, size_t o, uint32_t n) { for(unsigned i=0;i<4;++i)b[o+i]=uint8_t(n>>(8*i)); }
constexpr uint32_t base=0x10000, handler=base+0x200, imports=base+0x300, data=base+0x400;

std::vector<uint8_t> module(unsigned core, bool nested) {
    std::vector<uint8_t> image(0x600);
    image[0]=0x7f; image[1]='E'; image[2]='L'; image[3]='F'; image[4]=1; image[5]=1; image[6]=1;
    put16(image,16,2); put16(image,18,8); put32(image,20,1); put32(image,24,base); put32(image,28,52);
    put16(image,40,52); put16(image,42,32); put16(image,44,1);
    put32(image,52,1); put32(image,56,0x100); put32(image,60,base); put32(image,64,base);
    put32(image,68,0x500); put32(image,72,0x500); put32(image,76,7); put32(image,80,4);
    std::vector<uint32_t> code;
    const auto emit=[&](uint32_t word){code.push_back(word);};
    const auto imm=[&](unsigned reg,uint32_t n){emit(0x3c000000u|(reg<<16)|(n>>16));emit(0x34000000u|(reg<<21)|(reg<<16)|(n&0xffff));};
    const auto call=[&](unsigned index){emit(0x0c000000u|((imports+20+index*8)>>2));emit(0);};
    const auto pause=[&](){emit(0x24080200);emit(0x2508ffff);emit(0x1500fffe);emit(0);};
    const auto sample=[&](unsigned offset){imm(8,data);emit(0x8d090000);emit(0);emit(0xad090000|offset);};
    emit(0x27bdfff0); emit(0xafbf000c);
    imm(4,core?0x28:0x24); imm(5,1); imm(6,handler); imm(7,data); call(0); // RegisterIntrHandler
    imm(4,core?0x28:0x24); call(1); // EnableIntr
    if(nested) {
        imm(4,data+12);call(4); // CpuSuspendIntr saves enabled state
        imm(4,data+16);call(4); // Nested suspend saves disabled state
    } else call(2); // CpuDisableIntr
    imm(8,core?0x1f801504:0x1f8010c4);imm(9,0x00010020);emit(0xad090000); // BCR: 32 words
    imm(9,0x01000201);emit(0xad090004); // Start sound DMA; completion becomes pending while masked
    pause();sample(4);
    if(nested) {
        imm(8,data);emit(0x8d040010);emit(0);call(5); // Restore inner disabled state
        pause();sample(20);
        imm(8,data);emit(0x8d04000c);emit(0);call(5); // Restore outer enabled state
    } else call(3); // CpuEnableIntr
    pause();sample(8);pause();sample(24);
    emit(0x8fbf000c);emit(0x27bd0010);emit(0x03e00008);emit(0x00001021);
    check(code.size()*4<0x200,"Synthetic entry overlaps handler");
    for(size_t i=0;i<code.size();++i)put32(image,0x100+i*4,code[i]);
    const std::array<uint32_t,6> irq={0x8c820000,0,0x24420001,0xac820000,0x03e00008,0};
    for(size_t i=0;i<irq.size();++i)put32(image,0x300+i*4,irq[i]);
    put32(image,0x400,0x41e00000);put32(image,0x408,0x00000102);
    std::memcpy(image.data()+0x40c,"intrman",7);
    const unsigned ordinals[]={4,6,8,9,17,18};
    for(unsigned i=0;i<6;++i){put32(image,0x414+i*8,0x03e00008);put32(image,0x418+i*8,0x24000000|ordinals[i]);}
    return image;
}
}

int main() {
    for(unsigned core=0;core<2;++core)for(bool nested:{false,true}) {
        Host host;IopSubsystem iop(host);auto image=module(core,nested);
        check(host.writeGuest(0x100,image.data(),image.size()),"Cannot write synthetic module");
        auto loaded=iop.loadModuleBuffer(0x100);
        check(loaded.handled&&loaded.startResult==0,"Synthetic module did not return normally");
        std::array<uint32_t,7> result{};
        check(iop.readMemory(data,result.data(),sizeof(result)),"Cannot read interrupt observations");
        std::cout<<"core="<<core<<" nested="<<nested<<" masked="<<result[1]<<" resumed="<<result[2]<<" later="<<result[6]<<'\n';
        check(result[1]==0,"Sound DMA interrupt ran inside a masked IOP critical section");
        if(nested)check(result[3]==1&&result[4]==0&&result[5]==0,"Inner restore enabled IOP interrupts prematurely");
        check(result[2]==1&&result[6]==1,"Pending sound DMA interrupt was lost or delivered more than once");
    }
    std::cout<<"Both sound DMA cores defer masked interrupts and deliver once after outer restore\n";
}
