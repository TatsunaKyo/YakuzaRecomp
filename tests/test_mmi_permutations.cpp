// SPDX-License-Identifier: GPL-3.0-or-later
// Original-free R5900 lane-order and sprite-color regressions.
#include "ps2_runtime_macros.h"
#include <array>
#include <cstdint>
#include <iostream>

template <typename T, std::size_t N>
bool check(__m128i actual, const std::array<T, N>& expected, const char* label) {
    std::array<T, N> lanes{};
    _mm_storeu_si128(reinterpret_cast<__m128i*>(lanes.data()), actual);
    if (lanes == expected) return true;
    std::cerr << label << ": incorrect lanes:";
    for (auto value : lanes) std::cerr << ' ' << value;
    std::cerr << '\n';
    return false;
}

int main() {
    bool passed = true;
    const auto words = _mm_set_epi32(0x789abcde, 0x3456789a, 0x12345678, 0x01234567);
    passed &= check(PS2_PEXEW(words), std::array<uint32_t, 4>{
        0x3456789a, 0x12345678, 0x01234567, 0x789abcde}, "PEXEW");
    passed &= check(PS2_PROT3W(words), std::array<uint32_t, 4>{
        0x12345678, 0x3456789a, 0x01234567, 0x789abcde}, "PROT3W");
    const auto halves = _mm_set_epi16(0x789a, 0x6789, 0x5678, 0x4567, 0x3456, 0x2345, 0x1234, 0x0123);
    passed &= check(PS2_PEXEH(halves), std::array<uint16_t, 8>{
        0x2345, 0x1234, 0x0123, 0x3456, 0x6789, 0x5678, 0x4567, 0x789a}, "PEXEH");

    // Expand packed BGRA bytes, exchange red/blue, then round and halve.
    // An incorrect exchange sends the alpha byte into the blue channel.
    const auto spriteColor = [](uint32_t bgra) {
        auto channels = PS2_PEXTLB(_mm_setzero_si128(), _mm_cvtsi32_si128(static_cast<int32_t>(bgra)));
        channels = PS2_PEXTLH(_mm_setzero_si128(), channels);
        return _mm_srli_epi32(_mm_add_epi32(PS2_PEXEW(channels), _mm_set1_epi32(1)), 1);
    };
    passed &= check(spriteColor(0x80ffffff), std::array<uint32_t, 4>{128, 128, 128, 64}, "White sprite RGBA");
    passed &= check(spriteColor(0x80402010), std::array<uint32_t, 4>{32, 16, 8, 64}, "Distinct sprite RGBA");
    if (!passed) return 1;
    std::cout << "R5900 exchanges, rotation and packed sprite colors pass\n";
}
