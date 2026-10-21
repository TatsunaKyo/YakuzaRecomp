// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/boot_overlays.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include <algorithm>
#include <iostream>
#include <memory>
#include <stdexcept>

namespace yakuza {
namespace {
void check(bool condition, const char* detail) {
    if (!condition) throw std::runtime_error(detail);
}
std::unique_ptr<BootOverlayDispatch> dispatch;
PS2Runtime* owner = nullptr;
NativeFunction original_initialize = nullptr;

void initialize_overlay(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    check(runtime == owner && original_initialize && dispatch, "Overlay hook has no active runtime");
    const auto base = GPR_U32(context, 4) & PS2_RAM_MASK;
    if (base == OverlaySlot::start) {
        const uint32_t length = GPR_U32(context, 5);
        check(length >= 64 && length <= OverlaySlot::end - OverlaySlot::start,
              "Resident loader supplied an invalid overlay length");
        dispatch->activate(*runtime, std::span<const uint8_t>(memory + base, length));
    }
    // Preserve arguments, RA and all original loader/constructor behavior.
    original_initialize(memory, context, runtime);
}
}

void BootOverlayDispatch::activate(PS2Runtime& runtime, std::span<const uint8_t> image) {
    const auto layout = OverlaySlot::inspect(image);
    const BootOverlay* program = nullptr;
    for (const auto& candidate : programs_) {
        if (candidate.id != layout.id) continue;
        check(!program, "Duplicate compiled overlay identity");
        program = &candidate;
    }
    check(program && program->name == layout.name && program->file_size == image.size(),
          "Loaded overlay has no matching compiled translation");
    uint64_t digest = 0xcbf29ce484222325ULL;
    for (auto byte : image) digest = (digest ^ byte) * 0x100000001b3ULL;
    check(digest == program->fingerprint, "Loaded overlay differs from the translated original image");
    check(g_ps2RecompiledFunctionTableBase <= OverlaySlot::start &&
          g_ps2RecompiledFunctionTableEnd >= OverlaySlot::end &&
          uint64_t(g_ps2RecompiledFunctionTableSlotCount) * 4 >=
              uint64_t(OverlaySlot::end) - g_ps2RecompiledFunctionTableBase,
          "Native dispatch table does not contain the complete overlay slot");
    check(!program->entries.empty(), "Compiled overlay has no callable entries");
    uint32_t previous = 0;
    for (const auto& entry : program->entries) {
        check(entry.function && entry.address >= OverlaySlot::start + 64 &&
              entry.address < layout.file_end() && !(entry.address & 3) && entry.address > previous,
              "Invalid or unordered compiled overlay dispatch entry");
        previous = entry.address;
    }
    for (uint32_t constructor : layout.constructors) {
        if (!constructor) continue;
        const auto entry = std::lower_bound(program->entries.begin(), program->entries.end(), constructor,
            [](const NativeEntry& value, uint32_t address) { return value.address < address; });
        check(entry != program->entries.end() && entry->address == constructor,
              "Original overlay constructor has no compiled entry");
    }
    // All failure-prone validation precedes mutation. This runs on the EE
    // thread at the resident initialization boundary, before any constructor.
    // Clear the full slot so a shorter module cannot retain old callable PCs.
    for (uint32_t address = OverlaySlot::start; address < OverlaySlot::end; address += 4)
        runtime.replaceFunction(address, nullptr);
    for (const auto& entry : program->entries)
        runtime.replaceFunction(entry.address, entry.function);
    active_id_ = layout.id;
    ++generation_;
    std::cout << "[yakuza-overlay] verified " << layout.name << " id=" << layout.id
              << " bytes=" << image.size() << " entries=" << program->entries.size()
              << " constructors=" << layout.constructors.size() << " generation=" << generation_ << '\n';
}

void install_boot_overlay_hooks(PS2Runtime& runtime, std::span<const BootOverlay> programs) {
    if (programs.empty()) return;
    check(runtime.hasFunction(0x100350), "Missing original PAL overlay initializer");
    check(!owner || owner != &runtime, "Overlay hook is already installed");
    auto next = std::make_unique<BootOverlayDispatch>(programs);
    original_initialize = runtime.lookupFunction(0x100350);
    check(runtime.replaceFunction(0x100350, initialize_overlay), "Cannot bind original overlay initializer");
    dispatch = std::move(next);
    owner = &runtime;
}
} // namespace yakuza
