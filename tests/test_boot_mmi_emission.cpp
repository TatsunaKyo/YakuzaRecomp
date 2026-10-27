// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include <array>
#include <cstdint>
#include <iostream>

void synthetic_emitted_mmi(R5900Context*);
int main() {
    uint32_t seed = 0x12345678;
    for (unsigned trial = 0; trial < 257; ++trial) {
        std::array<uint16_t, 8> halves{}, expected_halves{}, actual_halves{};
        std::array<uint32_t, 4> words{}, expected_words{}, actual_words{};
        for (auto& value : halves) { seed = seed * 1664525u + 1013904223u; value = uint16_t(seed >> 8); }
        for (auto& value : words) { seed = seed * 1664525u + 1013904223u; value = seed; }
        for (unsigned half = 0; half < 2; ++half) {
            const unsigned base = half * 4;
            expected_halves[base] = halves[base + 2];
            expected_halves[base + 1] = halves[base + 1];
            expected_halves[base + 2] = halves[base];
            expected_halves[base + 3] = halves[base + 3];
        }
        for (unsigned word = 0; word < 3; ++word) expected_words[word] = words[(word + 1) % 3];
        expected_words[3] = words[3];
        R5900Context ctx{};
        ctx.r[8] = ctx.r[12] = _mm_loadu_si128(reinterpret_cast<const __m128i*>(halves.data()));
        ctx.r[10] = ctx.r[13] = _mm_loadu_si128(reinterpret_cast<const __m128i*>(words.data()));
        synthetic_emitted_mmi(&ctx);
        for (unsigned reg : {9u, 12u}) {
            _mm_storeu_si128(reinterpret_cast<__m128i*>(actual_halves.data()), ctx.r[reg]);
            if (actual_halves != expected_halves) { std::cerr << "Emitted PEXEH lane order differs\n"; return 1; }
        }
        for (unsigned reg : {11u, 13u}) {
            _mm_storeu_si128(reinterpret_cast<__m128i*>(actual_words.data()), ctx.r[reg]);
            if (actual_words != expected_words) { std::cerr << "Emitted PROT3W lane order differs\n"; return 1; }
        }
    }
    // Byte expansion, emitted PEXEH and byte packing must keep opaque alpha
    // out of the low RGB bytes, including an opaque black input.
    for (const auto& sample : std::array<std::array<uint32_t, 2>, 3>{{
             {{0x80000000u, 0x000000u}}, {{0x80402010u, 0x102040u}}, {{0x80ffffffu, 0xffffffu}}}}) {
        R5900Context ctx{};
        const auto packed = _mm_cvtsi32_si128(static_cast<int32_t>(sample[0]));
        ctx.r[8] = PS2_PEXTLB(_mm_setzero_si128(), packed);
        synthetic_emitted_mmi(&ctx);
        const auto result = PS2_PPACB(packed, ctx.r[9]);
        if ((uint32_t(_mm_cvtsi128_si32(result)) & 0xffffffu) != sample[1]) {
            std::cerr << "Emitted permutation corrupted packed RGB\n";
            return 1;
        }
    }
    std::cout << "257 emitted MMI vectors and three packed RGB cases pass, including aliased destinations\n";
}
