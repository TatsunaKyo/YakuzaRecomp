// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/overlay_slot.h"
#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <utility>

namespace yakuza {
namespace {
void check(bool value, const char* error) {
    if (!value) throw std::invalid_argument(error);
}
uint32_t word(std::span<const uint8_t> data, size_t position) {
    check(position <= data.size() && data.size() - position >= 4, "Truncated MWo3 word");
    return uint32_t(data[position]) | uint32_t(data[position + 1]) << 8 |
           uint32_t(data[position + 2]) << 16 | uint32_t(data[position + 3]) << 24;
}
} // namespace

OverlayLayout OverlaySlot::inspect(std::span<const uint8_t> image) {
    check(image.size() >= 64 && word(image, 0) == 0x336f574d, "Invalid MWo3 header");
    OverlayLayout layout{word(image, 4), word(image, 8), word(image, 12),
                         word(image, 16), word(image, 20), {}, {}};
    check(layout.id >= 2 && layout.id <= 12 && layout.address == start, "Unsupported gameplay overlay slot");
    check(layout.text_size && ((layout.text_size | layout.mixed_size | layout.bss_size) & 3) == 0,
          "Unaligned MWo3 region");
    const uint64_t file_size = uint64_t(64) + layout.text_size + layout.mixed_size;
    check(file_size == image.size() && file_size + layout.bss_size <= end - start,
          "Overlay exceeds its payload or shared slot");
    const auto name_end = std::find(image.begin() + 32, image.begin() + 64, 0);
    check(name_end != image.begin() + 64, "Unterminated MWo3 name");
    layout.name.assign(image.begin() + 32, name_end);
    check(layout.name.size() > 4 && layout.name.ends_with(".bin"), "Invalid MWo3 name");
    check(std::all_of(layout.name.begin(), layout.name.end(), [](unsigned char c) {
        return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '.';
    }), "Invalid MWo3 name characters");
    const uint32_t first = word(image, 24), last = word(image, 28);
    check(first >= start + 64 + layout.text_size && first <= last && last <= layout.file_end() &&
          ((first | last) & 3) == 0, "Invalid constructor table");
    layout.constructors.reserve((last - first) / 4);
    for (uint32_t address = first; address < last; address += 4) {
        const auto target = word(image, address - start);
        check(!target || (target >= start + 64 && target < layout.file_end() && !(target & 3)),
              "Constructor outside initialized overlay");
        layout.constructors.push_back(target);
    }
    return layout;
}

void OverlaySlot::activate(std::span<uint8_t> memory, std::span<const uint8_t> image,
                          std::span<const NativeEntry> entries) {
    // Allocate and validate before changing either guest memory or active code.
    auto candidate = inspect(image);
    check(memory.size() >= end, "EE memory does not contain the shared slot");
    std::vector<NativeEntry> table(entries.begin(), entries.end());
    std::sort(table.begin(), table.end(), [](auto& a, auto& b) { return a.address < b.address; });
    uint32_t previous = 0;
    for (auto& entry : table) {
        check(entry.function && entry.address >= start + 64 && entry.address < candidate.file_end() &&
              !(entry.address & 3) && entry.address != previous, "Invalid or duplicate native overlay entry");
        previous = entry.address;
    }
    // Copy first so an image view inside EE memory remains valid during a swap.
    std::vector<uint8_t> payload(image.begin(), image.end());
    std::memcpy(memory.data() + start, payload.data(), payload.size());
    std::fill_n(memory.data() + candidate.file_end(), candidate.bss_size, uint8_t(0));
    entries_.swap(table); // replaces ALL prior entries, including those past the new file end
    active_ = std::move(candidate);
    ++generation_;
}

NativeFunction OverlaySlot::lookup(uint32_t pc) const {
    auto it = std::lower_bound(entries_.begin(), entries_.end(), pc,
                               [](auto& entry, uint32_t address) { return entry.address < address; });
    return it != entries_.end() && it->address == pc ? it->function : nullptr;
}
} // namespace yakuza
