// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <span>
#include <string>
#include <vector>

namespace yakuza {
// Development-only original disc excerpts. Missing bytes never read as zeros.
class DiscRanges {
public:
    void load(const std::filesystem::path& directory);
    void add(const std::string& archive, uint64_t size, uint64_t offset, std::vector<uint8_t> bytes);
    std::optional<uint64_t> size(const std::string& archive) const;
    bool read(const std::string& archive, uint64_t offset, std::span<uint8_t> output) const;
private:
    struct Range { uint64_t offset; std::vector<uint8_t> bytes; };
    struct Archive { uint64_t size; std::vector<Range> ranges; };
    std::map<std::string, Archive> archives_;
};
} // namespace yakuza
