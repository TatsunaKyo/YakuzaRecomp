// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/pal_boot_hooks.h"
#include "ps2_runtime_macros.h"
#include "ps2_stubs.h"
#include "ps2_syscalls.h"
#include "runtime/ee_scheduler.h"
#include "pal_runtime_layout.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <utility>
#include <vector>

namespace yakuza {
namespace {
struct DmaCopy { uint32_t source, destination, size; };
std::vector<DmaCopy> dma_copies;

void reboot_iop(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    dma_copies.clear();
    ps2_stubs::sceSifRebootIop(memory, context, runtime);
}

void set_dma(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    const uint32_t descriptors = GPR_U32(context, 4) & PS2_RAM_MASK;
    const uint32_t count = GPR_U32(context, 5);
    if (count == 0 || count > 64 || count * 16 > PS2_RAM_SIZE - descriptors)
        throw std::runtime_error("Unsupported PAL SIF DMA descriptor list");
    std::vector<DmaCopy> copies;
    for (uint32_t i = 0; i < count; ++i) {
        const uint32_t record = descriptors + i * 16;
        DmaCopy copy{Ps2FastRead32(memory, record), Ps2FastRead32(memory, record + 4),
                     Ps2FastRead32(memory, record + 8)};
        const uint32_t offset = copy.source & PS2_RAM_MASK;
        if (!copy.size || copy.size > PS2_RAM_SIZE - offset ||
            !runtime->isIopMemoryRange(copy.destination, copy.size))
            throw std::runtime_error("Unsupported PAL EE-to-IOP DMA range");
        copies.push_back(copy);
    }
    // Keep the original transfer operation; remember only successful copies.
    ps2_stubs::sceSifSetDma(memory, context, runtime);
    if (!GPR_U32(context, 2)) return;
    for (auto copy : copies) {
        std::erase_if(dma_copies, [&](DmaCopy old) {
            return uint64_t(old.destination) < uint64_t(copy.destination) + copy.size &&
                   uint64_t(copy.destination) < uint64_t(old.destination) + old.size;
        });
        if (dma_copies.size() == 64) dma_copies.erase(dma_copies.begin());
        dma_copies.push_back(copy);
    }
}

void exec_iop_buffer(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    const uint32_t buffer = GPR_U32(context, 4);
    const auto found = std::find_if(dma_copies.rbegin(), dma_copies.rend(), [buffer](DmaCopy copy) {
        return buffer >= copy.destination && uint64_t(buffer) < uint64_t(copy.destination) + copy.size;
    });
    if (found == dma_copies.rend())
        throw std::runtime_error("IOP module buffer has no verified EE-to-IOP DMA source");
    const uint32_t skip = buffer - found->destination;
    const uint32_t source = (found->source & PS2_RAM_MASK) + skip, size = found->size - skip;
    std::vector<uint8_t> transferred(size);
    if (size < 52 || !runtime->readIopMemory(buffer, transferred.data(), size) ||
        !std::equal(transferred.begin(), transferred.end(), memory + source))
        throw std::runtime_error("Transferred IOP module differs from its original EE source");
    // The public module loader reads EE buffers. Verify that its complete ELF
    // image fits the matching transfer before supplying that original source.
    auto field = [&](uint32_t at) -> uint32_t {
        if (at > size - 4) throw std::runtime_error("IOP module ELF header exceeds the transfer");
        return Ps2FastRead32(memory, source + at);
    };
    auto contains = [&](uint64_t end) {
        if (end > size) throw std::runtime_error("IOP module ELF image exceeds the transfer");
    };
    if (field(0) != 0x464c457f || memory[source + 4] != 1 || memory[source + 5] != 1)
        throw std::runtime_error("Transferred IOP module is not a little-endian ELF32 image");
    for (unsigned table = 0; table < 2; ++table) {
        const uint32_t offset = field(table ? 32 : 28);
        const uint32_t counts = field(table ? 46 : 42);
        const uint32_t stride = counts & 0xffff, count = counts >> 16;
        if (count && stride < (table ? 40u : 32u))
            throw std::runtime_error("Invalid IOP module ELF table stride");
        contains(uint64_t(offset) + uint64_t(count) * stride);
        for (uint32_t i = 0; i < count; ++i) {
            const uint32_t entry = offset + i * stride;
            if (table && field(entry + 4) == 8) continue; // SHT_NOBITS
            contains(uint64_t(field(entry + (table ? 16 : 4))) + field(entry + (table ? 20 : 16)));
        }
    }
    const uint32_t argument = GPR_U32(context, 6) & PS2_RAM_MASK;
    const uint32_t length = GPR_U32(context, 6) ? std::min(GPR_U32(context, 5), 252u) : 0;
    const uint32_t result = GPR_U32(context, 7) & PS2_RAM_MASK;
    if (length > PS2_RAM_SIZE - argument || result > PS2_RAM_SIZE - 4)
        throw std::runtime_error("IOP module arguments or result exceed EE memory");
    const auto loaded = runtime->loadIopModuleBuffer(source, length ? memory + argument : nullptr, length);
    if (!loaded.handled || loaded.moduleId <= 0) {
        SET_GPR_S32(context, 2, -1);
        throw std::runtime_error("Native IOP loader rejected the transferred original module");
    }
    Ps2FastWrite32(memory, result, static_cast<uint32_t>(loaded.startResult));
    SET_GPR_S32(context, 2, loaded.moduleId);
    std::cout << "[yakuza-iop] executed transferred module iop=0x" << std::hex << buffer
              << " ee=0x" << source << std::dec << " id=" << loaded.moduleId
              << " start=" << loaded.startResult << '\n';
}
void firmware_patch_installer(uint8_t*, R5900Context* context, PS2Runtime*) {
    std::cout << "[yakuza-kernel] SDK firmware patch installer at 0x" << std::hex << context->pc
              << " uses native kernel services" << std::dec << '\n';
    SET_GPR_S32(context, 2, 0);
    context->pc = GPR_U32(context, 31);
}
template<void (*Handler)(uint8_t*, R5900Context*, PS2Runtime*)>
void sdk_service(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    static unsigned logged = 0;
    if (logged++ < 8)
        std::cout << "[yakuza-sdk] native SDK service for 0x" << std::hex << context->pc
                  << " a0=0x" << GPR_U32(context, 4) << " a1=0x" << GPR_U32(context, 5) << std::dec << '\n';
    if constexpr (Handler == ps2_syscalls::fioOpen || Handler == ps2_stubs::sceCdSearchFile) {
        const unsigned path_register = Handler == ps2_syscalls::fioOpen ? 4 : 5;
        const uint32_t address = GPR_U32(context, path_register) & PS2_RAM_MASK;
        std::string path;
        for (uint32_t i = address; i < PS2_RAM_SIZE && i - address < 512 && memory[i]; ++i)
            path += static_cast<char>(memory[i]);
        std::cout << "[yakuza-file] " << (Handler == ps2_syscalls::fioOpen ? "open " : "search ") << path << '\n';
        if constexpr (Handler == ps2_stubs::sceCdSearchFile) {
            if (GPR_U32(context, 6) != 0) {
                std::cout << "[yakuza-file] requested disc layer is not mounted\n";
                SET_GPR_S32(context, 2, 0); // SDK search failure; allow the original fallback handling.
                context->pc = GPR_U32(context, 31);
                return;
            }
        }
    }
    // Match the upstream generated HLE wrappers. A handler that transfers to
    // the scheduler must resume at the original caller, not inside SDK code.
    context->pc = GPR_U32(context, 31);
    Handler(memory, context, runtime);
}
void init_rpc(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    ps2_stubs::sceSifInitCmd(memory, context, runtime);
    ps2_syscalls::SifInitRpc(memory, context, runtime);
}
void init_heap(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    ps2_stubs::sceSifInitIopHeap(memory, context, runtime);
    if (GPR_S32(context, 2) == 0) Ps2FastWrite32(memory, 0x1323f0, 0);
}
void end_of_heap(uint8_t*, R5900Context* context, PS2Runtime*) {
    SET_GPR_U32(context, 2, pal_memory::game_heap_end);
}
void wait_vertical_blank(uint8_t*, R5900Context* context, PS2Runtime* runtime) {
    // The PAL SDK registers two stack locals with SetVSyncFlag, then polls
    // INTC_STAT. Native MMIO can satisfy that poll before the queued VBlank
    // writes those locals, leaving stale pointers into a returned stack frame.
    // Wait on the actual scheduler event instead, and retain the SDK's 64-bit
    // GS CSR return value (its caller extracts FIELD at bit 13).
    auto& scheduler = runtime->eeScheduler();
    const uint32_t resume = GPR_U32(context, 31);
    scheduler.waitVSync(scheduler.currentVSyncTick(), 0,
        [runtime, resume](R5900Context& resumed) {
            SET_GPR_U64((&resumed), 2, runtime->memory().gs().csr.load(std::memory_order_acquire));
            resumed.pc = resume;
        });
}
void debug_console(uint8_t* memory, R5900Context* context, PS2Runtime*) {
    // The PAL SDK's DECI2 console blocks awaiting a physical debug interface.
    // Preserve its actual write(buffer, length) operation through the host.
    const uint32_t address = GPR_U32(context, 4) & PS2_RAM_MASK;
    const int32_t length = GPR_S32(context, 5);
    if (length < 0 || length > 16384 || static_cast<uint32_t>(length) > PS2_RAM_SIZE - address) {
        SET_GPR_S32(context, 2, -1);
        return;
    }
    std::cout << "[yakuza-console] ";
    std::cout.write(reinterpret_cast<const char*>(memory + address), length);
    std::cout.flush();
    SET_GPR_S32(context, 2, std::cout ? length : -1);
}
} // namespace

void install_pal_kernel_hooks(PS2Runtime& runtime) {
    // Observed in the original CRT initialization chain at 0x10f518:
    // 0x10f408 installs FindAddress/copy syscalls and searches firmware for the
    // kernel table. With no firmware image it loops forever at 0x10f490.
    // The other three routines copy MIPS patches to firmware kernel addresses
    // and install those handlers. PS2Runtime supplies the corresponding native
    // kernel services; executing firmware patch code would corrupt their setup.
    // Keep all other CRT initialization: libc semaphores, timers, top thread,
    // and the final scratch structure initialization are original guest code.
    for (uint32_t address : {0x10f408u, 0x10f9f8u, 0x10f640u, 0x10eb30u}) {
        if (!runtime.hasFunction(address) || !runtime.replaceFunction(address, firmware_patch_installer))
            throw std::runtime_error("PAL kernel hook does not match the generated resident map");
    }
}

void install_pal_sdk_hooks(PS2Runtime& runtime) {
    // Identified from the PAL disassembly/decompilation: CMD initialization
    // waits on SREG[0]; RPC init installs command IDs 0x80000011/13; BindRpc
    // stores the SID and client pointer; CallRpc has the standard nine-argument
    // ABI and CheckStatRpc tests the client's active packet. These route to
    // implemented native services, rather than fabricated success returns.
    const std::pair<uint32_t, PS2Runtime::RecompiledFunction> services[] = {
        {0x108760u, sdk_service<ps2_stubs::sceSifInitCmd>},
        {0x10a028u, sdk_service<init_rpc>},
        {0x108f08u, sdk_service<ps2_syscalls::SifBindRpc>},
        {0x1090e8u, sdk_service<ps2_syscalls::SifCallRpc>},
        {0x1092e8u, sdk_service<ps2_syscalls::SifCheckStatRpc>},
        // CD initialization binds the physical CDVD service at SID 0x80000592.
        // The native CD backend mounts host files instead of an IOP CDVD IRX.
        {0x116138u, sdk_service<ps2_stubs::sceCdInit>},
        // The PAL reboot wrapper adds the UDNL prefix, then starts IOP reset;
        // Sync polls the SIF boot-ready flag. Use the runtime's IOP lifecycle.
        {0x10e8d0u, sdk_service<reboot_iop>},
        {0x10e880u, sdk_service<ps2_stubs::sceSifSyncIop>},
        {0x116d10u, sdk_service<ps2_stubs::sceCdMmode>},
        {0x116638u, sdk_service<ps2_stubs::sceCdDiskReady>},
        // Direct callees of the original pal_read_overlay_file: open(path,1),
        // seek(fd,0,2), seek(fd,0,0), read(fd,destination,size), close(fd).
        {0x10a528u, sdk_service<ps2_syscalls::fioOpen>},
        {0x10a930u, sdk_service<ps2_syscalls::fioLseek>},
        {0x10ab70u, sdk_service<ps2_syscalls::fioRead>},
        {0x10a7b8u, sdk_service<ps2_syscalls::fioClose>},
        // SID 0x80000003 is the IOP heap service. The original wrappers use
        // RPC 1(size) and RPC 2(pointer); the native allocator owns that heap.
        {0x10d450u, sdk_service<init_heap>},
        {0x10d4d8u, sdk_service<ps2_stubs::sceSifAllocIopHeap>},
        {0x10d5c8u, sdk_service<ps2_stubs::sceSifFreeIopHeap>},
        {0x1068f8u, sdk_service<debug_console>},
        // Layer search has the same file/path arguments; only layer zero is
        // mounted by this development host's virtual disc backend.
        {0x115910u, sdk_service<ps2_stubs::sceCdSearchFile>},
        // The virtual CD backend completes reads synchronously and retains the
        // real host-file error for GetError. It does not send CDVD RPC packets.
        {0x116858u, sdk_service<ps2_stubs::sceCdRead>},
        {0x115e20u, sdk_service<ps2_stubs::sceCdSync>},
        {0x115d88u, sdk_service<ps2_stubs::sceCdGetDiskType>},
        {0x116b08u, sdk_service<ps2_stubs::sceCdGetError>},
        {0x105560u, sdk_service<set_dma>},
        {0x10db68u, sdk_service<exec_iop_buffer>},
        {0x105180u, sdk_service<end_of_heap>},
        {0x1056c0u, sdk_service<wait_vertical_blank>},
    };
    for (const auto& [address, handler] : services) {
        if (!runtime.hasFunction(address) || !runtime.replaceFunction(address, handler))
            throw std::runtime_error("PAL SDK binding does not match the generated resident map");
    }
}
} // namespace yakuza
