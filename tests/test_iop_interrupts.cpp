// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic IOP module: sound DMA must respect global/nested interrupt masking.
// IopHost fixture follows the pinned PS2Recomp emulator-test interface.
#include "ps2x/iop/iop_subsystem.h"
#include "core/iop_cpu.h"
#include "core/iop_kernel.h"
#include "core/iop_memory.h"
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

void checkCriticalSectionAcrossSlices() {
    using namespace ps2x::iop::detail;
    IopMemory memory;
    IopKernel kernel(memory);
    IopCpuState caller{};
    const auto create=[&](unsigned priority) {
        const uint32_t descriptor=memory.allocate(32,16);
        memory.write32(descriptor+8,0x10000);
        memory.write32(descriptor+12,0x1000);
        memory.write32(descriptor+16,priority);
        caller.gpr[4]=descriptor;
        check(kernel.dispatchThreadImport(4,caller,0),"Cannot create synthetic IOP thread");
        return caller.gpr[2];
    };
    const auto start=[&](uint32_t id) {
        caller.gpr[4]=id;caller.gpr[5]=0;
        check(kernel.dispatchThreadImport(6,caller,0),"Cannot start synthetic IOP thread");
    };
    const auto high=create(20),low=create(30);
    start(high);
    auto* highThread=kernel.beginNextReady(0);
    check(highThread&&uint32_t(highThread->id)==high,"Higher-priority thread did not start");
    kernel.delayCurrentUntil(100,highThread->cpu);
    kernel.endTimeslice(*highThread,0xffffffff);
    start(low);
    auto* lowThread=kernel.beginNextReady(0);
    check(lowThread&&uint32_t(lowThread->id)==low,"Lower-priority thread did not start");
    memory.setInterruptControl(0);
    kernel.endTimeslice(*lowThread,0xffffffff); // Host budget ends in a guest critical section.
    auto* continued=kernel.beginNextReady(200); // The delayed high-priority thread's deadline has elapsed.
    check(continued==lowThread,"IOP host time slice preempted a masked critical section");
    memory.setInterruptControl(1);
    kernel.endTimeslice(*continued,0xffffffff);
    auto* resumed=kernel.beginNextReady(200);
    check(resumed==highThread,"Deferred higher-priority thread did not run after interrupt restore");
    kernel.delayCurrentUntil(400,highThread->cpu);
    kernel.endTimeslice(*highThread,0xffffffff);
    lowThread=kernel.beginNextReady(200);
    check(lowThread&&uint32_t(lowThread->id)==low,"Cannot resume lower-priority thread for explicit yield");
    memory.setInterruptControl(0);
    check(kernel.dispatchThreadImport(16,lowThread->cpu,200),"Cannot request an explicit guest yield");
    kernel.endTimeslice(*lowThread,0xffffffff);
    check(kernel.beginNextReady(500)==highThread,"Masked host-budget handling suppressed an explicit guest yield");
    memory.setInterruptControl(1);
    std::cout<<"IOP critical section survives host budget boundaries; priority scheduling resumes after restore\n";
}

// Phase 0 arms a one-shot timer and masks interrupts. Later modules restore
// the inner/outer saved mask without replacing the first module's counter.
std::vector<uint8_t> timerModule(bool nested, unsigned phase, bool delayedArgument=false) {
    const uint32_t load=base+phase*0x1000, timerImports=load+0x300, intrImports=load+0x380;
    std::vector<uint8_t> image(0x600);
    image[0]=0x7f;image[1]='E';image[2]='L';image[3]='F';image[4]=1;image[5]=1;image[6]=1;
    put16(image,16,2);put16(image,18,8);put32(image,20,1);put32(image,24,load);put32(image,28,52);
    put16(image,40,52);put16(image,42,32);put16(image,44,1);
    put32(image,52,1);put32(image,56,0x100);put32(image,60,load);put32(image,64,load);
    put32(image,68,0x500);put32(image,72,0x500);put32(image,76,7);put32(image,80,4);
    std::vector<uint32_t> code;
    const auto emit=[&](uint32_t word){code.push_back(word);};
    const auto imm=[&](unsigned reg,uint32_t n){emit(0x3c000000u|(reg<<16)|(n>>16));emit(0x34000000u|(reg<<21)|(reg<<16)|(n&0xffff));};
    const auto call=[&](uint32_t table,unsigned index){emit(0x0c000000u|((table+20+index*8)>>2));emit(0);};
    emit(0x27bdfff0);emit(0xafbf000c);emit(0xafb00008);
    if(phase==0) {
        imm(4,1);imm(5,32);imm(6,1);call(timerImports,0); // AllocHardTimer SYSCLK/32-bit
        emit(0x00408021); // Keep the allocated timer ID in s0.
        emit(0x02002021);imm(5,100);imm(6,handler);imm(7,data);call(timerImports,1);
        emit(0x02002021);imm(5,1);imm(6,0);imm(7,1);call(timerImports,2); // SetupHardTimer
        emit(0x02002021);call(timerImports,3); // StartHardTimer
        if(nested) {
            imm(4,data+12);call(intrImports,2); // Outer CpuSuspendIntr
            imm(4,data+16);call(intrImports,2); // Inner CpuSuspendIntr
        } else call(intrImports,0); // CpuDisableIntr
    } else if(nested) {
        imm(8,data);
        if(delayedArgument) {
            // The import thunk consumes the pending load before its real
            // function reads a0. Keep an opposite stale value to expose it.
            imm(4,phase==1?1:0);
            emit(0x0c000000u|((intrImports+20+3*8)>>2));
            emit(0x8d040000|(phase==1?16:12)); // lw a0 in the JAL delay slot.
        } else {
            emit(0x8d040000|(phase==1?16:12));emit(0);call(intrImports,3);
        }
    } else call(intrImports,1); // CpuEnableIntr
    emit(0x8fb00008);emit(0x8fbf000c);emit(0x27bd0010);emit(0x03e00008);emit(0x00001021);
    check(code.size()*4<0x200,"Synthetic timer entry overlaps handler");
    for(size_t i=0;i<code.size();++i)put32(image,0x100+i*4,code[i]);
    const std::array<uint32_t,7> irq={0x8c880000,0,0x25080001,0xac880000,0x00001021,0x03e00008,0};
    if(phase==0)for(size_t i=0;i<irq.size();++i)put32(image,0x300+i*4,irq[i]);
    const auto table=[&](size_t offset,const char* name,std::array<unsigned,4> ordinals) {
        put32(image,offset,0x41e00000);put32(image,offset+8,0x00000103);
        std::memcpy(image.data()+offset+12,name,7);
        for(unsigned i=0;i<4;++i){put32(image,offset+20+i*8,0x03e00008);put32(image,offset+24+i*8,0x24000000|ordinals[i]);}
    };
    table(0x400,"timrman",{4,20,22,23});table(0x480,"intrman",{8,9,17,18});
    return image;
}

void checkMaskedTimer(bool nested, bool delayedArgument=false) {
    Host host;IopSubsystem iop(host);
    const auto load=[&](unsigned phase) {
        auto image=timerModule(nested,phase,delayedArgument);
        check(host.writeGuest(0x100,image.data(),image.size()),"Cannot write synthetic timer module");
        auto result=iop.loadModuleBuffer(0x100);
        check(result.handled&&result.startResult==0,"Synthetic timer module did not return normally");
    };
    const auto count=[&]() {
        uint32_t n=0;check(iop.readMemory(data,&n,sizeof(n)),"Cannot read timer counter");return n;
    };
    load(0);iop.runEeCycles(8000);
    check(count()==0,"Timer interrupt ran inside a masked IOP critical section");
    if(nested) {
        load(1);iop.runEeCycles(8000);
        check(count()==0,"Timer interrupt ran after an inner disabled restore");
    }
    load(nested?2:1);iop.runEeCycles(8000);
    check(count()==1,"Pending timer interrupt was lost after outer restore");
    iop.runEeCycles(8000);
    check(count()==1,"One-shot timer interrupt was delivered more than once");
    std::cout<<"Timer interrupt respects "<<(nested?"nested":"ordinary")
             <<" interrupt masking; delay-slot argument="<<delayedArgument<<'\n';
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
    checkCriticalSectionAcrossSlices();
    checkMaskedTimer(false);
    checkMaskedTimer(true);
    checkMaskedTimer(true,true);
    std::cout<<"Both sound DMA cores defer masked interrupts and deliver once after outer restore\n";
}
