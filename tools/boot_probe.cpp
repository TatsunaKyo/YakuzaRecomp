// SPDX-License-Identifier: GPL-3.0-or-later
// Bounded full-runtime boot diagnostic. This is not a validated game release.
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_recompiled_functions.h"
#include "yakuza/pal_boot_hooks.h"
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#endif

namespace {
std::atomic<bool> reached_main{false}, finished{false};
void verify_input(const std::filesystem::path& path, uint64_t length, uint64_t expected) {
    if (std::filesystem::file_size(path) != length) throw std::runtime_error("Unsupported PAL input size");
    std::ifstream input(path, std::ios::binary);
    uint64_t fingerprint = 0xcbf29ce484222325ULL;
    char byte;
    while (input.get(byte)) fingerprint = (fingerprint ^ static_cast<uint8_t>(byte)) * 0x100000001b3ULL;
    if (!input.eof() || fingerprint != expected) throw std::runtime_error("Input differs from the supported PAL build");
}
void main_entry(uint8_t*, R5900Context* ctx, PS2Runtime* runtime) {
    reached_main.store(true);
    std::cout << "[yakuza-boot] reached original MAIN entry 0x22cc40; stopping at milestone\n" << std::flush;
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
    auto paths = PS2Runtime::getIoPaths();
    paths.mcRoot = std::filesystem::absolute(state / "mc0");
    PS2Runtime::setIoPaths(paths);
    yakuza::install_pal_kernel_hooks(runtime);
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
    return reached_main.load() ? 0 : 1;
}
} // namespace
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
    SetConsoleOutputCP(CP_UTF8);
#else
int main(int argc, char** argv) {
#endif
    if (argc < 2 || argc > 4) {
        std::cerr << "Usage: yakuza_boot_probe <original PAL disc folder> [max seconds, 1..120] [state folder]\n";
        return 2;
    }
    try {
        unsigned seconds = argc >= 3 ? static_cast<unsigned>(std::stoul(argv[2])) : 15;
        if (!seconds || seconds > 120) throw std::runtime_error("Time limit must be 1..120 seconds");
        auto state = argc == 4 ? std::filesystem::path(argv[3]) : std::filesystem::current_path() / ".yakuza-boot-state";
        return run(std::filesystem::path(argv[1]), seconds, state);
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
