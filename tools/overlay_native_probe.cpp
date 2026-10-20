// SPDX-License-Identifier: GPL-3.0-or-later
// RAM-only execution check for three small, genuine translated overlay routines.
// This does not instantiate a game runtime or execute overlay constructors.
#include "yakuza/overlay_slot.h"
#include "ps2_runtime_macros.h"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#endif

void game_FUN_006426e0_0x6426e0(uint8_t*, R5900Context*, PS2Runtime*);
void health_health_first_code_0x62dd00(uint8_t*, R5900Context*, PS2Runtime*);
void ufocatcher_ufocatcher_first_code_0x62dd00(uint8_t*, R5900Context*, PS2Runtime*);

// These routines should only access ordinary RAM. Hardware access fails loudly
// instead of supplying a successful fake device result. No PS2Runtime object is
// constructed or used by the tested RAM paths.
uint32_t PS2Runtime::Load32(uint8_t*, R5900Context*, uint32_t) {
    throw std::runtime_error("Unexpected hardware read in RAM-only probe");
}
void PS2Runtime::Store32(uint8_t*, R5900Context*, uint32_t, uint32_t) {
    throw std::runtime_error("Unexpected hardware write in RAM-only probe");
}
uint16_t PS2Runtime::Load16(uint8_t*, R5900Context*, uint32_t) {
    throw std::runtime_error("Unexpected hardware read in RAM-only probe");
}
void PS2Runtime::Store16(uint8_t*, R5900Context*, uint32_t, uint16_t) {
    throw std::runtime_error("Unexpected hardware write in RAM-only probe");
}
void PS2Runtime::Store8(uint8_t*, R5900Context*, uint32_t, uint8_t) {
    throw std::runtime_error("Unexpected hardware write in RAM-only probe");
}

namespace {
void check(bool condition, const char* detail) { if (!condition) throw std::runtime_error(detail); }
std::vector<uint8_t> read(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    check(bool(stream), "Cannot open overlay file");
    const auto length = stream.tellg();
    check(length >= 64 && length <= 1024 * 1024, "Invalid overlay file size");
    std::vector<uint8_t> data(static_cast<size_t>(length));
    stream.seekg(0);
    check(bool(stream.read(reinterpret_cast<char*>(data.data()), static_cast<std::streamsize>(data.size()))), "Short overlay read");
    return data;
}
int run(const std::filesystem::path& folder) {
    auto game = read(folder / "GAME.BIN"), health = read(folder / "HEALTH.BIN");
    auto ufo = read(folder / "UFOCATCHER.BIN");
    check(yakuza::OverlaySlot::inspect(game).id == 2 && yakuza::OverlaySlot::inspect(health).id == 8 &&
          yakuza::OverlaySlot::inspect(ufo).id == 3,
          "Unexpected PAL overlay IDs");
    // Full-image consistency fingerprints; SHA-256 validation is performed by
    // the preparation tool before analysis. No game instructions are embedded.
    auto fingerprint = [](const std::vector<uint8_t>& bytes) {
        uint64_t value = 0xcbf29ce484222325ULL;
        for (auto byte : bytes) value = (value ^ byte) * 0x100000001b3ULL;
        return value;
    };
    check(fingerprint(game) == 0xa15933f696ed5bf2ULL && fingerprint(health) == 0xd1a965551003e24dULL &&
          fingerprint(ufo) == 0x444601787229ab69ULL,
          "Overlay differs from the PAL probe build");
    std::vector<uint8_t> memory(32 * 1024 * 1024, 0xaa);
    auto* rdram = memory.data(); // used by upstream RAM macros below
    yakuza::OverlaySlot slot;
    // Exercise every original module through the loader before running selected
    // translated routines. Constructors are inspected, not executed here.
    size_t inspected_constructors = 0;
    for (const char* name : {"BACCARA", "BATTINGCENTER", "BLACKJACK", "CABARET", "CARCHASE", "GAME",
                             "HEALTH", "ODDOREVEN", "PACHISLOT", "ROULETTE", "UFOCATCHER"}) {
        auto image = read(folder / (std::string(name) + ".BIN"));
        slot.activate(memory, image, {});
        const auto* layout = slot.active();
        check(std::equal(image.begin(), image.end(), memory.begin() + layout->address), "Overlay copy mismatch");
        check(std::all_of(memory.begin() + layout->file_end(), memory.begin() + layout->file_end() + layout->bss_size,
                          [](uint8_t byte) { return byte == 0; }), "Overlay BSS mismatch");
        inspected_constructors += layout->constructors.size();
    }
    std::cout << "Loaded 11 original overlays; inspected " << inspected_constructors << " constructor pointers\n";
    constexpr uint32_t pc = 0x62dd00, object = 0x10000, return_pc = 0x1fffffc;
    constexpr uint32_t game_pc = 0x6426e0;
    const yakuza::NativeEntry game_table[] = {{game_pc, game_FUN_006426e0_0x6426e0}};
    const yakuza::NativeEntry health_table[] = {{pc, health_health_first_code_0x62dd00}};
    const yakuza::NativeEntry ufo_table[] = {{pc, ufocatcher_ufocatcher_first_code_0x62dd00}};
    uint32_t random = 0x54171;
    size_t cases = 0;
    // Repeated real switches at the same guest PC also expose stale dispatch.
    for (unsigned round = 0; round < 8; ++round) {
        slot.activate(memory, game, game_table);
        for (unsigned i = 0; i < 32; ++i) {
            random = random * 1664525u + 1013904223u;
            const uint16_t value = i < 8 ? uint16_t(i * 15) : uint16_t(random);
            FAST_WRITE16(object + 0x6fe, value);
            FAST_WRITE16(object + 0x7c8, 0xffff);
            FAST_WRITE32(object + 0x22c4, 0x12345678);
            R5900Context ctx{}; auto* context = &ctx;
            SET_GPR_U32(context, 4, object); SET_GPR_U32(context, 5, random);
            SET_GPR_U32(context, 31, return_pc); ctx.pc = game_pc;
            slot.lookup(game_pc)(rdram, &ctx, nullptr);
            check(FAST_READ16(object + 0x7c8) == std::min<unsigned>(value / 2, 30) &&
                  FAST_READ32(object + 0x22c4) == 7 && FAST_READ8(object + 0x7c5) == uint8_t(random),
                  "GAME clamp/branch-likely/delay-slot mismatch");
            check(ctx.pc == return_pc && !ctx.in_delay_slot, "GAME return state mismatch");
            ++cases;
        }
        slot.activate(memory, health, health_table);
        check(slot.lookup(pc) == health_health_first_code_0x62dd00 && !slot.lookup(game_pc), "Stale GAME dispatch");
        for (unsigned i = 0; i < 32; ++i) {
            random = random * 1664525u + 1013904223u;
            FAST_WRITE32(object + 0x670, random);
            R5900Context ctx{}; auto* context = &ctx;
            SET_GPR_U32(context, 4, object); SET_GPR_U32(context, 31, return_pc); ctx.pc = pc;
            slot.lookup(pc)(rdram, &ctx, nullptr);
            check(GPR_U64(context, 2) == static_cast<uint64_t>(static_cast<int64_t>(static_cast<int32_t>(random))),
                  "HEALTH delay-slot load/sign extension mismatch");
            check(ctx.pc == return_pc && !ctx.in_delay_slot, "HEALTH return state mismatch");
            ++cases;
        }
        slot.activate(memory, ufo, ufo_table);
        check(slot.lookup(pc) == ufocatcher_ufocatcher_first_code_0x62dd00, "Stale HEALTH dispatch");
        for (unsigned i = 0; i < 32; ++i) {
            R5900Context ctx{}; auto* context = &ctx;
            SET_GPR_U32(context, 2, random); SET_GPR_U32(context, 31, return_pc); ctx.pc = pc;
            slot.lookup(pc)(rdram, &ctx, nullptr);
            check(GPR_U64(context, 2) == 0 && ctx.pc == return_pc && !ctx.in_delay_slot, "UFO return delay-slot mismatch");
            ++cases;
        }
    }
    std::cout << cases << " translated GAME/HEALTH/UFO cases passed; total overlay activations: " << slot.generation() << '\n';
    return 0;
}
} // namespace
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
    SetConsoleOutputCP(CP_UTF8);
#else
int main(int argc, char** argv) {
#endif
    if (argc != 2) { std::cerr << "Usage: yakuza_overlay_native_probe <extracted MEDIA4/MODULE folder>\n"; return 2; }
    try { return run(std::filesystem::path(argv[1])); }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
