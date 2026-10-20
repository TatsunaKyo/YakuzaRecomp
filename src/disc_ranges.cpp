// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/disc_ranges.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace yakuza {
namespace {
constexpr uint64_t max_range = 24 * 1024 * 1024, max_total = 512 * 1024 * 1024;
constexpr std::array<uint8_t, 8> magic{'Y','K','R','A','N','G','E',1};
void require(bool ok) { if (!ok) throw std::runtime_error("Invalid original-disc range collection"); }
uint64_t word(std::span<const uint8_t> header, size_t at) {
    uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) value |= uint64_t(header[at + i]) << (i * 8);
    return value;
}
}
void DiscRanges::add(const std::string& name, uint64_t size, uint64_t offset, std::vector<uint8_t> bytes) {
    require(name == "OGRE.CVM" || name == "OGRE2.CVM" || name == "OGRE3.CVM" || name == "OGRE4.CVM");
    require(size > 0 && size <= UINT32_MAX && offset < size && !bytes.empty() &&
            bytes.size() <= max_range && bytes.size() <= size - offset);
    auto found = archives_.find(name);
    uint64_t total = bytes.size();
    for (const auto& [_, archive] : archives_)
        for (const auto& range : archive.ranges) total += range.bytes.size();
    require(total <= max_total);
    if (found != archives_.end()) {
        require(found->second.size == size);
        for (const auto& old : found->second.ranges) {
            const auto begin = std::max(offset, old.offset);
            const auto end = std::min(offset + bytes.size(), old.offset + old.bytes.size());
            if (begin < end)
                require(std::equal(bytes.begin() + (begin - offset), bytes.begin() + (end - offset),
                                   old.bytes.begin() + (begin - old.offset)));
        }
    }
    auto& archive = archives_.try_emplace(name, Archive{size, {}}).first->second;
    archive.ranges.push_back({offset, std::move(bytes)});
    std::sort(archive.ranges.begin(), archive.ranges.end(), [](const Range& a, const Range& b) { return a.offset < b.offset; });
}
std::optional<uint64_t> DiscRanges::size(const std::string& name) const {
    auto found = archives_.find(name);
    if (found == archives_.end()) return std::nullopt;
    return found->second.size;
}
bool DiscRanges::read(const std::string& name, uint64_t offset, std::span<uint8_t> output) const {
    auto found = archives_.find(name);
    if (found == archives_.end() || offset > found->second.size || output.size() > found->second.size - offset) return false;
    // Validate complete coverage first. Failed requests leave destination unchanged.
    uint64_t cursor = offset, end = offset + output.size();
    for (const auto& range : found->second.ranges) {
        if (range.offset > cursor) break;
        cursor = std::max(cursor, range.offset + range.bytes.size());
        if (cursor >= end) break;
    }
    if (cursor < end) return false;
    cursor = offset;
    for (const auto& range : found->second.ranges) {
        const uint64_t begin = std::max(cursor, range.offset);
        const uint64_t stop = std::min(end, range.offset + range.bytes.size());
        if (begin < stop) {
            std::copy_n(range.bytes.begin() + (begin - range.offset), stop - begin, output.begin() + (begin - offset));
            cursor = stop;
        }
        if (cursor == end) break;
    }
    return true;
}
void DiscRanges::load(const std::filesystem::path& directory) {
    DiscRanges pending;
    if (std::filesystem::exists(directory)) {
        size_t count = 0;
        for (const auto& entry : std::filesystem::directory_iterator(directory)) {
            require(++count <= 4096 && entry.is_regular_file() && !entry.is_symlink());
            const auto name = entry.path().filename().string();
            const auto marker = name.find(".CVM.");
            require(marker != std::string::npos && name.ends_with(".ykr"));
            const auto length = entry.file_size();
            require(length > 40 && length <= max_range + 40);
            std::ifstream file(entry.path(), std::ios::binary);
            std::array<uint8_t, 40> header{};
            file.read(reinterpret_cast<char*>(header.data()), header.size());
            require(file.good() && std::equal(magic.begin(), magic.end(), header.begin()));
            require(word(header, 24) == length - 40);
            std::ostringstream expected_name;
            expected_name << name.substr(0, marker + 4) << '.' << std::hex << std::setw(16)
                          << std::setfill('0') << word(header, 16) << ".ykr";
            require(name == expected_name.str());
            std::vector<uint8_t> data(length - 40);
            file.read(reinterpret_cast<char*>(data.data()), data.size());
            require(file.good());
            uint64_t digest = 0xcbf29ce484222325ULL;
            for (auto b : data) digest = (digest ^ b) * 0x100000001b3ULL;
            require(digest == word(header, 32));
            pending.add(name.substr(0, marker + 4), word(header, 8), word(header, 16), std::move(data));
        }
    }
    archives_ = std::move(pending.archives_);
}
} // namespace yakuza
