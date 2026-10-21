// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic full-runtime overlay dispatch test; no original game or display.
#include "yakuza/boot_overlays.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ee_scheduler.h"
#include <algorithm>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <vector>

using namespace yakuza;
namespace {
constexpr uint32_t pc = OverlaySlot::start + 64, old_pc = OverlaySlot::start + 200;
bool initialized = false;
void check(bool value) { if (!value) throw std::runtime_error("Boot overlay dispatch regression"); }
void one(uint8_t*, R5900Context* ctx, PS2Runtime*) {
    SET_GPR_U32(ctx, 2, 1); ctx->pc = GPR_U32(ctx, 31);
}
void two(uint8_t*, R5900Context* ctx, PS2Runtime*) {
    SET_GPR_U32(ctx, 2, 2); ctx->pc = GPR_U32(ctx, 31);
}
void original_initializer(uint8_t*, R5900Context* ctx, PS2Runtime* runtime) {
    check(GPR_U32(ctx, 4) == OverlaySlot::start && runtime->hasFunction(pc));
    initialized = true;
    ctx->pc = GPR_U32(ctx, 31);
}
void put(std::vector<uint8_t>& data, size_t at, uint32_t value) {
    for (size_t i = 0; i < 4; ++i) data.at(at + i) = uint8_t(value >> (i * 8));
}
std::vector<uint8_t> image(uint32_t id, uint32_t text) {
    std::vector<uint8_t> data(64 + text + 16);
    uint32_t words[]{0x336f574d, id, OverlaySlot::start, text, 16, 32,
                     OverlaySlot::start + 64 + text, OverlaySlot::start + 68 + text};
    for (size_t i = 0; i < 8; ++i) put(data, i * 4, words[i]);
    std::memcpy(data.data() + 32, "test.bin", 9);
    std::fill(data.begin() + 64, data.begin() + 64 + text, uint8_t(id));
    put(data, 64 + text, pc);
    return data;
}
uint64_t fingerprint(std::span<const uint8_t> data) {
    uint64_t result = 0xcbf29ce484222325ULL;
    for (auto byte : data) result = (result ^ byte) * 0x100000001b3ULL;
    return result;
}
}
int main() {
    PS2Runtime runtime;
    check(runtime.memory().initialize());
    auto* memory = runtime.memory().getRDRAM();
    auto large = image(2, 256), small = image(3, 64);
    NativeEntry entries_a[]{{pc, one}, {old_pc, one}}, entries_b[]{{pc, two}};
    const BootOverlay programs[]{
        {2, "test.bin", uint32_t(large.size()), fingerprint(large), entries_a},
        {3, "test.bin", uint32_t(small.size()), fingerprint(small), entries_b}};
    BootOverlayDispatch dispatch(programs);
    std::fill_n(memory, PS2_RAM_SIZE, uint8_t{0xaa});
    std::copy(large.begin(), large.end(), memory + OverlaySlot::start);
    const std::vector<uint8_t> before(memory, memory + PS2_RAM_SIZE);
    check(runtime.replaceFunction(0x100100, one));
    dispatch.activate(runtime, std::span<const uint8_t>(memory + OverlaySlot::start, large.size()));
    check(dispatch.generation() == 1 && dispatch.active_id() == 2 && runtime.hasFunction(old_pc));
    check(std::equal(before.begin(), before.end(), memory)); // no payload or BSS writes
    dispatch.activate(runtime, small);
    check(dispatch.generation() == 2 && dispatch.active_id() == 3 && !runtime.hasFunction(old_pc));
    check(runtime.lookupFunction(pc) == two && runtime.lookupFunction(0x100100) == one);
    R5900Context context{};
    context.pc = pc; SET_GPR_U32((&context), 31, 0x100100);
    runtime.eeScheduler().reset(memory, context);
    check(runtime.dispatchGuestBranch(memory, &context, pc, 0x1000f8, 0x100100,
        PS2Runtime::GuestBranchKind::DirectCall, "synthetic overlay call"));
    check(context.pc == 0x100100 && GPR_U32((&context), 2) == 2);
    for (unsigned corruption = 0; corruption < 4; ++corruption) {
        auto bad = small;
        if (corruption == 0) bad[70] ^= 1;
        if (corruption == 1) put(bad, 4, 4);
        if (corruption == 2) put(bad, 20, 0xffffffff);
        if (corruption == 3) bad.pop_back();
        bool rejected = false;
        try { dispatch.activate(runtime, bad); } catch (const std::exception&) { rejected = true; }
        check(rejected && dispatch.generation() == 2 && runtime.lookupFunction(pc) == two);
    }
    NativeEntry invalid_entries[]{{pc + 4, one}}; // constructor missing
    BootOverlay invalid{2, "test.bin", uint32_t(large.size()), fingerprint(large), invalid_entries};
    BootOverlayDispatch missing_ctor(std::span<const BootOverlay>(&invalid, 1));
    bool rejected = false;
    try { missing_ctor.activate(runtime, large); } catch (const std::exception&) { rejected = true; }
    check(rejected && runtime.lookupFunction(pc) == two && !runtime.hasFunction(old_pc));
    // The real resident initializer remains in charge of initialization.
    std::copy(large.begin(), large.end(), memory + OverlaySlot::start);
    check(runtime.replaceFunction(0x100350, original_initializer));
    install_boot_overlay_hooks(runtime, programs);
    context = R5900Context{}; context.pc = 0x100350;
    SET_GPR_U32((&context), 4, OverlaySlot::start);
    SET_GPR_U32((&context), 5, uint32_t(large.size()));
    SET_GPR_U32((&context), 31, 0x100100);
    runtime.lookupFunction(0x100350)(memory, &context, &runtime);
    check(initialized && context.pc == 0x100100 && runtime.lookupFunction(pc) == one);
    std::cout << "Loaded-image verification, overlay swapping, constructor coverage and resident handoff passed\n";
}
