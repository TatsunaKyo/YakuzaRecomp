// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/disc_ranges.h"
#include <array>
#include <iostream>
#include <stdexcept>
#include <limits>
#include <chrono>
#include <fstream>

void check(bool value) { if (!value) throw std::runtime_error("Disc range regression"); }
template<class F> void rejects(F&& f) {
    try { f(); } catch (const std::runtime_error&) { return; }
    throw std::runtime_error("Invalid disc collection was accepted");
}
int main() {
    yakuza::DiscRanges ranges;
    ranges.add("OGRE.CVM", 12, 0, {1,2,3});
    ranges.add("OGRE.CVM", 12, 3, {4,5,6});
    ranges.add("OGRE.CVM", 12, 2, {3,4,5,6,7});
    std::array<uint8_t, 6> output{};
    check(ranges.size("OGRE.CVM") == 12 && !ranges.size("OGRE2.CVM"));
    check(ranges.read("OGRE.CVM", 1, output) && output == std::array<uint8_t,6>{2,3,4,5,6,7});
    output.fill(0xcc);
    check(!ranges.read("OGRE.CVM", 4, output));
    check(output == std::array<uint8_t,6>{0xcc,0xcc,0xcc,0xcc,0xcc,0xcc});
    check(!ranges.read("OGRE.CVM", std::numeric_limits<uint64_t>::max(), output));
    rejects([&] { ranges.add("OGRE.CVM", 12, 2, {0}); });
    rejects([&] { ranges.add("OGRE.CVM", 13, 8, {1}); });
    rejects([&] { ranges.add("../OGRE.CVM", 12, 0, {1}); });
    rejects([&] { ranges.add("OGRE.CVM", 12, 12, {1}); });
    ranges.add("OGRE.CVM", 12, 9, {10,11,12});
    output.fill(0xcc);
    check(!ranges.read("OGRE.CVM", 6, output)); // A hole between two known ranges.
    check(output[0] == 0xcc && output[5] == 0xcc);
    const auto temp = std::filesystem::temp_directory_path() /
        ("yakuza-disc-ranges-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    check(std::filesystem::create_directory(temp));
    try {
        const auto file = temp / "OGRE.CVM.0000000000000000.ykr";
        std::vector<uint8_t> encoded{'Y','K','R','A','N','G','E',1};
        auto append = [&](uint64_t value) { for (unsigned i = 0; i < 8; ++i) encoded.push_back(static_cast<uint8_t>(value >> (i * 8))); };
        append(12); append(0); append(4);
        uint64_t digest = 0xcbf29ce484222325ULL;
        for (uint8_t b : {1,2,3,4}) digest = (digest ^ b) * 0x100000001b3ULL;
        append(digest);
        encoded.insert(encoded.end(), {1,2,3,4});
        auto write = [&] {
            std::ofstream stream(file, std::ios::binary | std::ios::trunc);
            stream.write(reinterpret_cast<const char*>(encoded.data()), encoded.size());
            check(stream.good());
        };
        write();
        ranges.load(temp);
        std::array<uint8_t,4> loaded{};
        check(ranges.read("OGRE.CVM", 0, loaded) && loaded == std::array<uint8_t,4>{1,2,3,4});
        encoded.back() ^= 1; write();
        rejects([&] { ranges.load(temp); });
        check(ranges.read("OGRE.CVM", 0, loaded) && loaded[3] == 4); // Failed reload preserves mounted data.
        encoded.pop_back(); write();
        rejects([&] { ranges.load(temp); });
        std::filesystem::remove_all(temp);
    } catch (...) { std::filesystem::remove_all(temp); throw; }
    std::cout << "Original extent reads, overlap consistency, holes and bounds passed\n";
}
