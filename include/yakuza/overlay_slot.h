// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <span>
#include <string>
#include <vector>

struct R5900Context;
class PS2Runtime;

namespace yakuza {
using NativeFunction = void (*)(uint8_t*, R5900Context*, PS2Runtime*);
struct NativeEntry {
    uint32_t address;
    NativeFunction function;
};
struct OverlayLayout {
    uint32_t id, address, text_size, mixed_size, bss_size;
    std::string name;
    std::vector<uint32_t> constructors;
    uint32_t file_end() const { return address + 64 + text_size + mixed_size; }
};

// Only one gameplay/minigame overlay occupies this address range at a time.
// Activation must happen on the stopped EE thread, outside a translated call.
// Constructor execution and PS2Runtime lookup integration are the caller's job.
class OverlaySlot {
public:
    static constexpr uint32_t start = 0x62dc80;
    static constexpr uint32_t end = 0x6ef500;
    static OverlayLayout inspect(std::span<const uint8_t> image);
    void activate(std::span<uint8_t> ee_memory, std::span<const uint8_t> image,
                  std::span<const NativeEntry> entries);
    NativeFunction lookup(uint32_t pc) const;
    const OverlayLayout* active() const { return generation_ ? &active_ : nullptr; }
    uint64_t generation() const { return generation_; }
private:
    OverlayLayout active_{};
    std::vector<NativeEntry> entries_;
    uint64_t generation_ = 0;
};
} // namespace yakuza
