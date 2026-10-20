// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/overlay_slot.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>

using yakuza::OverlaySlot;
void check(bool condition) { if (!condition) throw std::runtime_error("Overlay slot regression"); }
void one(uint8_t*, R5900Context*, PS2Runtime*) {}
void two(uint8_t*, R5900Context*, PS2Runtime*) {}
void put(std::vector<uint8_t>& b, size_t p, uint32_t value) {
    for (size_t i = 0; i < 4; ++i) b.at(p + i) = uint8_t(value >> (i * 8));
}
std::vector<uint8_t> fixture(uint32_t id, uint32_t text) {
    std::vector<uint8_t> data(64 + text + 16, 0);
    const uint32_t header[] = {0x336f574d, id, OverlaySlot::start, text, 16, 32,
                              OverlaySlot::start + 64 + text, OverlaySlot::start + 68 + text};
    for (size_t i = 0; i < 8; ++i) put(data, i * 4, header[i]);
    const std::string name = "test.bin";
    std::copy(name.begin(), name.end(), data.begin() + 32);
    std::fill(data.begin() + 64, data.begin() + 64 + text, uint8_t(id));
    put(data, 64 + text, OverlaySlot::start + 64);
    return data;
}
int main() {
    std::vector<uint8_t> memory(32 * 1024 * 1024, 0xaa);
    OverlaySlot slot;
    auto large = fixture(2, 256), small = fixture(3, 64);
    const yakuza::NativeEntry old_table[] = {{OverlaySlot::start + 64, one}, {OverlaySlot::start + 200, one}};
    slot.activate(memory, large, old_table);
    check(slot.generation() == 1 && slot.lookup(OverlaySlot::start + 64) == one);
    check(memory[OverlaySlot::start - 1] == 0xaa && memory[OverlaySlot::start + large.size()] == 0);
    check(memory[OverlaySlot::start + large.size() + 32] == 0xaa);
    const yakuza::NativeEntry new_table[] = {{OverlaySlot::start + 64, two}};
    slot.activate(memory, small, new_table);
    check(slot.generation() == 2 && slot.lookup(OverlaySlot::start + 64) == two);
    check(!slot.lookup(OverlaySlot::start + 200) && !slot.lookup(OverlaySlot::start - 4));
    check(slot.active()->constructors == std::vector<uint32_t>{OverlaySlot::start + 64});
    const auto before = memory;
    for (int corruption = 0; corruption < 5; ++corruption) {
        auto bad = small;
        if (corruption == 0) put(bad, 12, 0xffffffff);
        if (corruption == 1) put(bad, 20, 0xffffffff);
        if (corruption == 2) put(bad, 28, 0xffffffff);
        if (corruption == 3) put(bad, 128, OverlaySlot::end);
        if (corruption == 4) bad.pop_back();
        bool rejected = false;
        try { slot.activate(memory, bad, new_table); } catch (const std::invalid_argument&) { rejected = true; }
        check(rejected && memory == before && slot.generation() == 2 && slot.lookup(OverlaySlot::start + 64) == two);
    }
    const yakuza::NativeEntry duplicate[] = {new_table[0], new_table[0]};
    bool rejected = false;
    try { slot.activate(memory, small, duplicate); } catch (const std::invalid_argument&) { rejected = true; }
    check(rejected && memory == before && slot.generation() == 2);
    // A view into guest memory is supported, too.
    slot.activate(memory, std::span<const uint8_t>(memory.data() + OverlaySlot::start, small.size()), new_table);
    check(slot.generation() == 3);
    std::cout << "Overlay swap, BSS, constructor bounds and atomic rejection checks passed\n";
}
