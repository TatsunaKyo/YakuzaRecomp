// SPDX-License-Identifier: GPL-3.0-or-later
// Bounded full-runtime boot diagnostic. This is not a validated game release.
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ee_scheduler.h"
#include "ps2_recompiled_functions.h"
#include "yakuza/pal_boot_hooks.h"
#include "yakuza/boot_overlays.h"
#include "pal_runtime_layout.h"
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#endif

namespace {
std::atomic<bool> reached_main{false}, finished{false};
bool continue_main = false;
PS2Runtime::RecompiledFunction original_main = nullptr;
void dump_graphics(PS2Runtime& runtime, const std::filesystem::path& folder) {
    std::filesystem::create_directories(folder);
    std::ofstream trace(folder / "gs-trace.txt");
    const auto snapshot = runtime.gs().getDebugSnapshot();
    for (unsigned i = 0; i < 2; ++i) {
        const auto& ctx = snapshot.ctx[i];
        const auto& tex = ctx.tex0;
        trace << "context=" << i << " frame=" << ctx.frame.fbp << ',' << ctx.frame.fbw
              << ',' << unsigned(ctx.frame.psm) << " tex=" << tex.tbp0 << ',' << unsigned(tex.tbw)
              << ',' << unsigned(tex.psm) << ',' << unsigned(tex.tw) << ',' << unsigned(tex.th)
              << " clut=" << tex.cbp << ',' << unsigned(tex.cpsm) << ',' << unsigned(tex.csm)
              << ',' << unsigned(tex.csa) << ',' << unsigned(tex.cld)
              << " clamp=" << ctx.clamp << " test=" << ctx.test << " alpha=" << ctx.alpha << '\n';
    }
    for (const auto& event : runtime.gs().getDebugHistory()) {
        const auto& tex = event.tex0;
        trace << "event=" << unsigned(event.kind) << " seq=" << event.seq << " vsync=" << event.vsyncTick
              << " reg=" << unsigned(event.reg) << " value=" << event.regValue
              << " prim=" << unsigned(event.prim.type) << ',' << unsigned(event.prim.tme)
              << " frame=" << event.frame.fbp << ',' << event.frame.fbw << ',' << unsigned(event.frame.psm)
              << " tex=" << tex.tbp0 << ',' << unsigned(tex.tbw) << ',' << unsigned(tex.psm)
              << ',' << unsigned(tex.tw) << ',' << unsigned(tex.th)
              << " clut=" << tex.cbp << ',' << unsigned(tex.cpsm) << ',' << unsigned(tex.csm)
              << ',' << unsigned(tex.csa) << ',' << unsigned(tex.cld)
              << " xy=" << event.xMin << ',' << event.xMax << ',' << event.yMin << ',' << event.yMax << '\n';
    }
    if (!trace) throw std::runtime_error("Cannot write private graphics trace");
    runtime.gs().refreshDisplaySnapshot();
    uint32_t size = 0;
    const auto* vram = runtime.gs().lockDisplaySnapshot(size);
    std::ofstream memory(folder / "gs-vram.bin", std::ios::binary);
    if (vram && size) memory.write(reinterpret_cast<const char*>(vram), size);
    runtime.gs().unlockDisplaySnapshot();
    if (!vram || !memory || size != PS2_GS_VRAM_SIZE) throw std::runtime_error("Cannot write complete private GS memory");
    std::ofstream ee(folder / "ee-ram.bin", std::ios::binary);
    ee.write(reinterpret_cast<const char*>(runtime.memory().getRDRAM()), PS2_RAM_SIZE);
    if (!ee) throw std::runtime_error("Cannot write private EE graphics source memory");
    std::cout << "[yakuza-gs] saved private graphics trace, VRAM and EE source memory in state/graphics\n";
}
void verify_input(const std::filesystem::path& path, uint64_t length, uint64_t expected) {
    if (std::filesystem::file_size(path) != length) throw std::runtime_error("Unsupported PAL input size");
    std::ifstream input(path, std::ios::binary);
    uint64_t fingerprint = 0xcbf29ce484222325ULL;
    char byte;
    while (input.get(byte)) fingerprint = (fingerprint ^ static_cast<uint8_t>(byte)) * 0x100000001b3ULL;
    if (!input.eof() || fingerprint != expected) throw std::runtime_error("Input differs from the supported PAL build");
}
void main_entry(uint8_t* memory, R5900Context* ctx, PS2Runtime* runtime) {
    uint64_t code = 0xcbf29ce484222325ULL;
    for (uint32_t i = 0; i < 3026720; ++i) code = (code ^ memory[0x167c40 + i]) * 0x100000001b3ULL;
    if (Ps2FastRead32(memory, 0x167c00) != 0x336f574d || code != 0xcf4017352c7cb639ULL)
        throw std::runtime_error("MAIN entry reached without the verified original code loaded into RAM");
    if (runtime->guestHeapEnd() != runtime->guestHeapBase())
        throw std::runtime_error("Native helper allocations exist before the PAL MAIN heap handoff");
    runtime->configureGuestHeap(yakuza::pal_memory::native_heap_start, yakuza::pal_memory::native_heap_end);
    reached_main.store(true);
    std::cout << "[yakuza-boot] verified original MAIN payload at entry 0x22cc40\n" << std::flush;
    if (continue_main) {
        original_main(memory, ctx, runtime);
        return;
    }
    std::cout << "[yakuza-boot] stopping at first-boot milestone\n";
    runtime->requestStop();
    ctx->pc = 0x22cc40;
}
int run(const std::filesystem::path& folder, unsigned seconds, const std::filesystem::path& state) {
    if (!std::filesystem::is_regular_file(folder / "SLES_541.71") ||
        !std::filesystem::is_regular_file(folder / "MAIN.BIN"))
        throw std::runtime_error("PAL disc folder must contain SLES_541.71 and MAIN.BIN");
    verify_input(folder / "SLES_541.71", 354320, 0x8cc141f490fa8854ULL);
    verify_input(folder / "MAIN.BIN", 4367488, 0xbc3620cf6abcbe29ULL);
    PS2Runtime runtime;
    runtime.setMissingFunctionPolicy(PS2Runtime::MissingFunctionPolicy::Stop);
    if (!runtime.initialize("YakuzaRecomp | PAL boot development probe")) return 2;
    if (!runtime.loadELF((folder / "SLES_541.71").string())) return 2;
#ifdef _WIN32
    char graphics_env[2]{};
    const bool graphics_trace = continue_main &&
        GetEnvironmentVariableA("YAKUZA_BOOT_DUMP_GS", graphics_env, sizeof(graphics_env)) == 1 && graphics_env[0] == '1';
#else
    const char* graphics_env = std::getenv("YAKUZA_BOOT_DUMP_GS");
    const bool graphics_trace = continue_main && graphics_env && std::string_view(graphics_env) == "1";
#endif
    if (graphics_trace) runtime.gs().setDebugHistoryPaused(false);
    auto paths = PS2Runtime::getIoPaths();
    paths.mcRoot = std::filesystem::absolute(state / "mc0");
    PS2Runtime::setIoPaths(paths);
    yakuza::install_pal_kernel_hooks(runtime);
    yakuza::install_pal_sdk_hooks(runtime);
    yakuza::install_boot_supplement(runtime);
    yakuza::install_boot_overlay_hooks(runtime, yakuza::compiled_boot_overlays());
    original_main = runtime.lookupFunction(0x22cc40);
    if (!original_main) throw std::runtime_error("Missing original MAIN entry in the generated dispatch map");
    if (!runtime.replaceFunction(0x22cc40, main_entry)) throw std::runtime_error("MAIN entry is outside dispatch table");
    std::thread watchdog([&] {
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
        while (!finished.load() && std::chrono::steady_clock::now() < deadline)
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        if (!finished.load()) {
            std::cerr << "[yakuza-boot] time limit reached; requesting a stop\n";
            runtime.requestStop();
        }
    });
    try { runtime.run(); }
    catch (...) { finished.store(true); watchdog.join(); throw; }
    finished.store(true); watchdog.join();
    std::cout << "[yakuza-boot] final PC=0x" << std::hex << runtime.cpu().pc << std::dec
              << " reached_main=" << reached_main.load() << '\n';
    if (continue_main) {
        const auto iop = runtime.iopDebugSnapshot();
        std::cout << "[yakuza-runtime] vsync=" << runtime.eeScheduler().currentVSyncTick()
                  << " dma=" << runtime.memory().dmaStartCount()
                  << " gif=" << runtime.memory().gifCopyCount()
                  << " gs=" << runtime.memory().gsWriteCount()
                  << " vif=" << runtime.memory().vifWriteCount()
                  << " iop_modules=" << iop.emulatorLoadedModules
                  << " iop_threads=" << iop.emulatorThreads
                  << " iop_rpc_servers=" << iop.emulatorRpcServers
                  << " iop_instructions=" << iop.emulatorInstructions << '\n';
        for (const auto& diagnostic : iop.diagnostics)
            std::cout << "[yakuza-iop-diagnostic] " << diagnostic << '\n';
        runtime.eeScheduler().publishSnapshot();
        const auto ee = runtime.eeScheduler().snapshot();
        std::cout << "[yakuza-ee] running=" << ee.runningThreadId << " cycles=" << ee.eeCycle << '\n';
        for (const auto& thread : ee.threads)
            std::cout << "[yakuza-ee-thread] id=" << thread.id << " priority=" << thread.currentPriority
                      << " status=" << static_cast<unsigned>(thread.status)
                      << " wait=" << static_cast<unsigned>(thread.waitReason) << " wait_id=" << thread.waitId
                      << " pc=0x" << std::hex << thread.pc << " entry=0x" << thread.entry
                      << " ra=0x" << thread.ra << std::dec << '\n';
        for (const auto& semaphore : ee.semaphores)
            if (semaphore.waiters)
                std::cout << "[yakuza-ee-semaphore] id=" << semaphore.id << " count=" << semaphore.count
                          << " waiters=" << semaphore.waiters << '\n';
        for (unsigned reg = 1; reg < 32; ++reg)
            std::cout << "[yakuza-register] r" << reg << "=0x" << std::hex
                      << GPR_U64((&runtime.cpu()), reg) << std::dec << '\n';
        if (graphics_trace) dump_graphics(runtime, state / "graphics");
    }
    // Continued exploration has no success end condition yet. Keep failures or
    // time limits distinct from the deliberate successful MAIN checkpoint.
    return reached_main.load() && !continue_main ? 0 : 1;
}
} // namespace
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
    SetConsoleOutputCP(CP_UTF8);
#else
int main(int argc, char** argv) {
#endif
    std::cout << std::unitbuf;
    if (argc < 2 || argc > 5) {
        std::cerr << "Usage: yakuza_boot_probe <original PAL disc folder> [max seconds, 1..120] [state folder] [continue]\n";
        return 2;
    }
    try {
        unsigned seconds = argc >= 3 ? static_cast<unsigned>(std::stoul(argv[2])) : 15;
        if (!seconds || seconds > 120) throw std::runtime_error("Time limit must be 1..120 seconds");
        auto state = argc >= 4 ? std::filesystem::path(argv[3]) : std::filesystem::current_path() / ".yakuza-boot-state";
        if (argc == 5) {
            if (std::filesystem::path(argv[4]) != "continue") throw std::runtime_error("Unknown boot mode");
            continue_main = true;
        }
        return run(std::filesystem::path(argv[1]), seconds, state);
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
