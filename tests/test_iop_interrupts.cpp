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
#include <utility>
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
std::vector<uint8_t> timerModule(bool nested, unsigned phase, bool delayedArgument=false, bool disc=false) {
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
        if(disc) {
            imm(4,0);call(timerImports,2); // sceCdInit
            imm(4,handler);call(timerImports,0); // sceCdCallback
            imm(4,0);call(timerImports,1); // sceCdSeek: synthetic completion needs no disc data.
        } else {
        imm(4,1);imm(5,32);imm(6,1);call(timerImports,0); // AllocHardTimer SYSCLK/32-bit
        emit(0x00408021); // Keep the allocated timer ID in s0.
        emit(0x02002021);imm(5,100);imm(6,handler);imm(7,data);call(timerImports,1);
        emit(0x02002021);imm(5,1);imm(6,0);imm(7,1);call(timerImports,2); // SetupHardTimer
        emit(0x02002021);call(timerImports,3); // StartHardTimer
        }
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
    if(phase==0) {
        if(disc) {
            const std::array<uint32_t,9> completion={0x3c080001,0x35080400,0x8d090000,0,0x25290001,0xad090000,0xad04001c,0x03e00008,0x00001021};
            for(size_t i=0;i<completion.size();++i)put32(image,0x300+i*4,completion[i]);
        } else for(size_t i=0;i<irq.size();++i)put32(image,0x300+i*4,irq[i]);
    }
    const auto table=[&](size_t offset,const char* name,std::array<unsigned,4> ordinals) {
        put32(image,offset,0x41e00000);put32(image,offset+8,0x00000103);
        std::memcpy(image.data()+offset+12,name,7);
        for(unsigned i=0;i<4;++i){put32(image,offset+20+i*8,0x03e00008);put32(image,offset+24+i*8,0x24000000|ordinals[i]);}
    };
    if(disc)table(0x400,"cdvdman",{37,7,4,0});
    else table(0x400,"timrman",{4,20,22,23});
    table(0x480,"intrman",{8,9,17,18});
    return image;
}

void checkMaskedTimer(bool nested, bool delayedArgument=false, bool disc=false) {
    Host host;IopSubsystem iop(host);
    const auto load=[&](unsigned phase) {
        auto image=timerModule(nested,phase,delayedArgument,disc);
        check(host.writeGuest(0x100,image.data(),image.size()),"Cannot write synthetic timer module");
        auto result=iop.loadModuleBuffer(0x100);
        check(result.handled&&result.startResult==0,"Synthetic timer module did not return normally");
    };
    const auto count=[&]() {
        uint32_t n=0;check(iop.readMemory(data,&n,sizeof(n)),"Cannot read timer counter");return n;
    };
    load(0);iop.runEeCycles(8000);
    check(count()==0,disc?"Disc completion callback ran inside a masked IOP critical section":"Timer interrupt ran inside a masked IOP critical section");
    if(nested) {
        load(1);iop.runEeCycles(8000);
        check(count()==0,"Timer interrupt ran after an inner disabled restore");
    }
    load(nested?2:1);iop.runEeCycles(8000);
    check(count()==1,"Pending timer interrupt was lost after outer restore");
    iop.runEeCycles(8000);
    check(count()==1,"One-shot timer interrupt was delivered more than once");
    if(disc) {
        uint32_t reason=0;check(iop.readMemory(data+28,&reason,sizeof(reason)),"Cannot read disc completion reason");
        check(reason==4,"Disc seek completion lost its original reason argument");
    }
    std::cout<<(disc?"Disc completion":"Timer interrupt")<<" respects "<<(nested?"nested":"ordinary")
             <<" interrupt masking; delay-slot argument="<<delayedArgument<<'\n';
}

constexpr uint32_t criticalRpcSid=0xF00D0325u, criticalRpcData=base+0x700;
std::vector<uint8_t> rpcCriticalModule(bool resumable) {
    constexpr uint32_t worker=base+0x200, rpc=base+0x300;
    constexpr uint32_t intr=base+0x400, threads=base+0x500, sif=base+0x600;
    constexpr uint32_t descriptor=base+0x740, server=base+0x780, buffer=base+0x7c0;
    std::vector<uint8_t> image(0x900);
    image[0]=0x7f;image[1]='E';image[2]='L';image[3]='F';image[4]=1;image[5]=1;image[6]=1;
    put16(image,16,2);put16(image,18,8);put32(image,20,1);put32(image,24,base);put32(image,28,52);
    put16(image,40,52);put16(image,42,32);put16(image,44,1);
    put32(image,52,1);put32(image,56,0x100);put32(image,60,base);put32(image,64,base);
    put32(image,68,0x800);put32(image,72,0x800);put32(image,76,7);put32(image,80,4);
    std::vector<uint32_t> code;
    const auto emit=[&](uint32_t word){code.push_back(word);};
    const auto imm=[&](unsigned reg,uint32_t n){emit(0x3c000000u|(reg<<16)|(n>>16));emit(0x34000000u|(reg<<21)|(reg<<16)|(n&0xffff));};
    const auto call=[&](uint32_t table,unsigned index){emit(0x0c000000u|((table+20+index*8)>>2));emit(0);};
    const auto write=[&](uint32_t address) {
        check(code.size()*4<0x100,"Synthetic RPC routine overlaps the next section");
        for(size_t i=0;i<code.size();++i)put32(image,0x100+address-base+i*4,code[i]);
        code.clear();
    };
    emit(0x27bdffe0);emit(0xafbf001c);
    imm(4,server);imm(5,criticalRpcSid);imm(6,rpc);imm(7,buffer);
    emit(0xafa00010);emit(0xafa00014);emit(0xafa00018);call(sif,0);
    if(resumable) {
    imm(8,descriptor);imm(9,worker);emit(0xad090008);
    imm(9,0x1000);emit(0xad09000c);imm(9,30);emit(0xad090010);
    imm(4,descriptor);call(threads,0);emit(0x00402021);imm(5,0);call(threads,1);
    } else {
        imm(8,criticalRpcData);imm(9,1);emit(0xad090000);call(intr,0);
    }
    emit(0x8fbf001c);emit(0x27bd0020);emit(0x03e00008);emit(0x00001021);write(base);
    emit(0x27bdfff0);emit(0xafbf000c);call(intr,0); // Begin a real guest-thread critical section.
    imm(8,criticalRpcData);imm(9,1);emit(0xad090000);
    emit(0x240a0400);emit(0x254affff);emit(0x1540fffe);emit(0); // More than one host slice.
    emit(0xad000000);call(intr,1);
    emit(0x8fbf000c);emit(0x27bd0010);emit(0x03e00008);emit(0);write(worker);
    imm(8,criticalRpcData);emit(0x8d090000);emit(0);emit(0xad090004);
    emit(0x01001021);emit(0x03e00008);emit(0);write(rpc);
    const auto table=[&](uint32_t address,const char* name,const std::vector<unsigned>& ordinals) {
        const size_t offset=0x100+address-base;put32(image,offset,0x41e00000);put32(image,offset+8,0x00000101);
        std::memcpy(image.data()+offset+12,name,7);
        for(size_t i=0;i<ordinals.size();++i){put32(image,offset+20+i*8,0x03e00008);put32(image,offset+24+i*8,0x24000000|ordinals[i]);}
    };
    table(intr,"intrman",{8,9});table(threads,"thbase",{4,6});table(sif,"sifcmd",{17});
    return image;
}

void checkRpcCriticalSection(bool resumable) {
    Host host;IopSubsystem iop(host);const auto image=rpcCriticalModule(resumable);
    check(host.writeGuest(0x100,image.data(),image.size()),"Cannot write synthetic critical-section RPC module");
    auto loaded=iop.loadModuleBuffer(0x100);
    check(loaded.handled&&loaded.startResult==0,"Critical-section RPC module did not return normally");
    check(iop.canBindRpc(criticalRpcSid),"Synthetic RPC server was not registered");
    iop.runEeCycles(800); // Leave the worker inside its masked section at the host boundary.
    uint32_t active=0;check(iop.readMemory(criticalRpcData,&active,sizeof(active)),"Cannot inspect synthetic critical section");
    check(active==1,"Synthetic RPC precondition did not reach the critical section");
    RpcRequest request{};request.sid=criticalRpcSid+1;request.receive={0xe00,8};
    const auto instructions=iop.debugSnapshot().emulatorInstructions;
    check(!iop.handleRpc(request).handled,"Unknown RPC server unexpectedly handled");
    check(iop.debugSnapshot().emulatorInstructions==instructions,"Unknown RPC request advanced the guest critical section");
    request.sid=criticalRpcSid;
    if(!resumable) {
        bool rejected=false;
        try { (void)iop.handleRpc(request); }
        catch(const std::runtime_error& error) {
            rejected=std::string(error.what()).find("critical section")!=std::string::npos;
        }
        check(rejected,"RPC entered a masked context without a resumable guest thread");
        std::array<uint32_t,2> untouched{};
        check(iop.readMemory(criticalRpcData,untouched.data(),sizeof(untouched)),"Cannot inspect blocked RPC state");
        check(untouched[0]==1&&untouched[1]==0,"Blocked RPC altered the synthetic critical section");
        std::cout<<"Unresumable masked RPC fails with a diagnostic and preserves guest data\n";
        return;
    }
    check(iop.handleRpc(request).handled,"Synthetic critical-section RPC was not dispatched");
    std::array<uint32_t,2> observed{};check(host.readGuest(0xe00,observed.data(),sizeof(observed)),"Cannot read synthetic RPC observation");
    check(observed[1]==0,"IOP RPC handler preempted a masked guest thread");
    std::cout<<"Known RPC handler waits for the guest critical section; unknown requests leave it alone\n";
}

constexpr uint32_t queueSid=0xF00D0326u, queueData=base+0x900;
std::vector<uint8_t> rpcQueueModule(unsigned workerPriority, bool delayHandler, bool stuckHandler=false) {
    constexpr uint32_t worker=base+0x200, handler=base+0x300, serverThread=base+0x400;
    constexpr uint32_t threads=base+0x600, sif=base+0x700;
    constexpr uint32_t descriptor=base+0x940, server=base+0x980, buffer=base+0x9c0, queue=base+0xa00;
    std::vector<uint8_t> image(0xc00);
    image[0]=0x7f;image[1]='E';image[2]='L';image[3]='F';image[4]=1;image[5]=1;image[6]=1;
    put16(image,16,2);put16(image,18,8);put32(image,20,1);put32(image,24,base);put32(image,28,52);
    put16(image,40,52);put16(image,42,32);put16(image,44,1);
    put32(image,52,1);put32(image,56,0x100);put32(image,60,base);put32(image,64,base);
    put32(image,68,0xb00);put32(image,72,0xb00);put32(image,76,7);put32(image,80,4);
    std::vector<uint32_t> code;
    const auto emit=[&](uint32_t word){code.push_back(word);};
    const auto imm=[&](unsigned reg,uint32_t n){emit(0x3c000000u|(reg<<16)|(n>>16));emit(0x34000000u|(reg<<21)|(reg<<16)|(n&0xffff));};
    const auto call=[&](uint32_t table,unsigned index){emit(0x0c000000u|((table+20+index*8)>>2));emit(0);};
    const auto write=[&](uint32_t address) {
        check(code.size()*4<0x200,"Synthetic queued RPC routine overlaps next section");
        for(size_t i=0;i<code.size();++i)put32(image,0x100+address-base+i*4,code[i]);
        code.clear();
    };
    emit(0x27bdffe0);emit(0xafbf001c);
    for(auto spec: {std::pair{worker,workerPriority},std::pair{serverThread,30u}}) {
        imm(8,descriptor);imm(9,spec.first);emit(0xad090008);
        imm(9,0x1000);emit(0xad09000c);imm(9,spec.second);emit(0xad090010);
        imm(4,descriptor);call(threads,0);emit(0x00402021);imm(5,0);call(threads,1);
    }
    emit(0x8fbf001c);emit(0x27bd0020);emit(0x03e00008);emit(0);write(base);
    emit(0x27bdfff0);emit(0xafbf000c);imm(4,10);call(threads,3); // Let server enter its RPC loop first.
    imm(8,queueData);imm(9,1);emit(0xad090000);
    emit(0x240a0400);emit(0x254affff);emit(0x1540fffe);emit(0); // Split an unmasked work item across host budgets.
    emit(0x8d090000);emit(0);emit(0xad090004); // Observe whether RPC destroyed the live buffer.
    imm(9,1);emit(0xad090008);call(threads,4); // Complete, then SleepThread.
    emit(0x8fbf000c);emit(0x27bd0010);emit(0x03e00008);emit(0);write(worker);
    emit(0x27bdfff0);emit(0xafbf000c);
    if(stuckHandler){emit(0x1000ffff);emit(0);}
    if(delayHandler){imm(4,10);call(threads,3);}
    call(threads,2);imm(8,queueData);emit(0xad02000c); // GetThreadId must identify registered server.
    emit(0xad1d0010);emit(0xad000000); // Save real server SP; destroy buffer.
    emit(0x8d090008);emit(0);emit(0xad090014); // Completion marker at dispatch.
    emit(0x8d090018);emit(0);emit(0x25290001);emit(0xad090018); // Calls must not re-enter initialization.
    emit(0x01001021);emit(0x8fbf000c);emit(0x27bd0010);emit(0x03e00008);emit(0);write(handler);
    emit(0x27bdffe0);emit(0xafbf001c);
    call(threads,2);emit(0x00402821);imm(4,queue);call(sif,1);
    imm(4,server);imm(5,queueSid);imm(6,handler);imm(7,buffer);
    emit(0xafa00010);emit(0xafa00014);imm(8,queue);emit(0xafa80018);call(sif,0);
    imm(4,queue);call(sif,2); // RpcLoop sleeps until a request.
    emit(0x8fbf001c);emit(0x27bd0020);emit(0x03e00008);emit(0);write(serverThread);
    const auto table=[&](uint32_t address,const char* name,const std::vector<unsigned>& ordinals) {
        const size_t offset=0x100+address-base;put32(image,offset,0x41e00000);put32(image,offset+8,0x00000101);
        std::memcpy(image.data()+offset+12,name,7);
        for(size_t i=0;i<ordinals.size();++i){put32(image,offset+20+i*8,0x03e00008);put32(image,offset+24+i*8,0x24000000|ordinals[i]);}
    };
    table(threads,"thbase",{4,6,20,33,24});table(sif,"sifcmd",{17,19,22});
    return image;
}

void checkRpcQueue(unsigned priority, bool delayHandler) {
    Host host;IopSubsystem iop(host);const auto image=rpcQueueModule(priority,delayHandler);
    check(host.writeGuest(0x100,image.data(),image.size()),"Cannot write queued RPC fixture");
    check(iop.loadModuleBuffer(0x100).startResult==0,"Queued RPC fixture failed to initialize");
    iop.runEeCycles(4800);
    check(iop.canBindRpc(queueSid),"Queued RPC server did not reach its loop");
    std::array<uint32_t,7> before{};check(iop.readMemory(queueData,before.data(),sizeof(before)),"Cannot inspect queued RPC precondition");
    check(before[0]==1&&before[2]==0,"Queued RPC fixture must stop partway through worker's live buffer use");
    RpcRequest request{};request.sid=queueSid;request.receive={0xe00,28};
    check(iop.handleRpc(request).handled,"Queued RPC was not handled");
    std::array<uint32_t,7> after{};check(host.readGuest(0xe00,after.data(),sizeof(after)),"Cannot inspect queued RPC reply");
    if(priority<30) {
        check(after[5]==1&&after[1]==1,"Queued RPC destroyed a buffer before its higher-priority worker finished");
    } else if(!delayHandler) check(after[5]==0,"Lower-priority worker incorrectly delayed RPC dispatch");
    check(after[3]==2,"Queued RPC executed outside its registered server thread");
    check(after[4]>=0x100000&&after[4]<0x1f0000,"Queued RPC did not use the server's allocated stack");
    check(after[6]==1,"Queued RPC callback did not complete exactly once");
    check(iop.handleRpc(request).handled,"Second queued RPC was not handled");
    check(host.readGuest(0xe00,after.data(),sizeof(after))&&after[6]==2&&after[3]==2,"Server did not return to its RPC loop after callback");
    std::cout<<"Queued RPC follows original thread priority/context and completes after waits; worker priority="<<priority<<", delay="<<delayHandler<<'\n';
}


void checkAutoDmaClock() {
    using namespace ps2x::iop::detail;
    IopMemory memory;
    for(unsigned core=0;core<2;++core) {
        const uint32_t chcr=core?0x1f801508:0x1f8010c8;
        const uint32_t admas=core?0x1f9005b0:0x1f9001b0;
        const auto transfer=[&](uint16_t mode,uint32_t direction) {
            memory.write16(admas,mode);
            memory.write32(chcr-4,0x00100020); // 512 32-bit words = 512 stereo PCM16 frames.
            memory.write32(chcr,0x01000200|direction);
            const auto dma=memory.takeDmaStart();check(dma.has_value(),"SPU DMA start was lost");return *dma;
        };
        check(transfer(0,1).delayCycles==1024,"Ordinary SPU DMA timing changed");
        check(transfer(uint16_t(core+1),1).delayCycles==393216,"AutoDMA completion ignores 48 kHz stereo consumption");
        check(transfer(uint16_t(core+1),0).delayCycles==1024,"SPU DMA read incorrectly uses playback clock");
        check(transfer(uint16_t(core?1:2),1).delayCycles==1024,"Wrong core's AutoDMA bit changes transfer timing");
    }
    std::cout<<"Both AutoDMA cores consume stereo PCM16 at 48kHz; ordinary/read DMA paths retain timing\n";
}

void checkRpcQueueGuard() {
    Host host;IopSubsystem iop(host);const auto image=rpcQueueModule(60,false,true);
    check(host.writeGuest(0x100,image.data(),image.size()),"Cannot write stuck queued RPC fixture");
    check(iop.loadModuleBuffer(0x100).startResult==0,"Stuck queued RPC fixture failed to initialize");
    iop.runEeCycles(4800);
    std::array<uint32_t,7> before{},after{};
    check(iop.readMemory(queueData,before.data(),sizeof(before))&&before[0]==1,"Invalid stuck RPC precondition");
    RpcRequest request{};request.sid=queueSid;
    const auto start=iop.debugSnapshot().emulatorInstructions;
    bool rejected=false;
    try{(void)iop.handleRpc(request);}
    catch(const std::runtime_error& error){rejected=std::string(error.what()).find("call budget")!=std::string::npos;}
    check(rejected,"Nonreturning queued RPC was incorrectly reported complete");
    check(iop.debugSnapshot().emulatorInstructions-start<=2'000'000,"Queued RPC exceeded existing call guard");
    check(iop.readMemory(queueData,after.data(),sizeof(after))&&before==after,"RPC guard changed guest markers or forced completion");
    std::cout<<"Nonreturning queued RPC retains existing call guard and diagnostic guest state\n";
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
    checkMaskedTimer(false,false,true);
    checkMaskedTimer(true,false,true);
    checkAutoDmaClock();
    checkRpcQueue(10,false);
    checkRpcQueue(60,false);
    checkRpcQueue(10,true);
    checkRpcQueue(60,true);
    checkRpcQueueGuard();
    checkRpcCriticalSection(true);
    checkRpcCriticalSection(false);
    std::cout<<"Both sound DMA cores defer masked interrupts and deliver once after outer restore\n";
}
