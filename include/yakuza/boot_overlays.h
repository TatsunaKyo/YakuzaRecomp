// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "yakuza/overlay_slot.h"
#include <string_view>

namespace yakuza {
struct BootOverlay {
    uint32_t id;
    std::string_view name;
    uint32_t file_size;
    uint64_t fingerprint;
    std::span<const NativeEntry> entries;
};

// Bind only an already loaded, verified image. The original resident loader
// retains responsibility for BSS clearing and constructor execution.
class BootOverlayDispatch {
public:
    explicit BootOverlayDispatch(std::span<const BootOverlay> programs) : programs_(programs) {}
    void activate(PS2Runtime& runtime, std::span<const uint8_t> image);
    uint64_t generation() const { return generation_; }
    uint32_t active_id() const { return active_id_; }
private:
    std::span<const BootOverlay> programs_;
    uint64_t generation_ = 0;
    uint32_t active_id_ = 0;
};

std::span<const BootOverlay> compiled_boot_overlays();
void install_boot_overlay_hooks(PS2Runtime& runtime, std::span<const BootOverlay> programs);
} // namespace yakuza
