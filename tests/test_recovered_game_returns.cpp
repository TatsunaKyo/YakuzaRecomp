#include "ps2_runtime.h"
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <vector>
#include <type_traits>

void game_verified_table_0069ff40_0x69ff40(uint8_t*, R5900Context*, PS2Runtime*);
void game_verified_table_0069ff50_0x69ff50(uint8_t*, R5900Context*, PS2Runtime*);

int main() {
    static_assert(std::is_trivially_copyable_v<R5900Context>);
    using Fn = void (*)(uint8_t*, R5900Context*, PS2Runtime*);
    const std::array<std::pair<uint32_t, Fn>, 2> methods{{
        {0x69ff40, game_verified_table_0069ff40_0x69ff40},
        {0x69ff50, game_verified_table_0069ff50_0x69ff50}}};
    const std::array<uint32_t, 8> returns{{0,0x100000,0x29c4cc,0x636660,0x7ffffffc,0x80001000,0xa0001000,0xfffffffc}};
    std::vector<uint8_t> ram(1 << 20, 0x5a);
    const auto original_ram = ram;
    unsigned cases = 0;
    for (auto [entry, method] : methods) for (uint32_t target : returns) for (uint32_t pattern=1; pattern<=8; ++pattern) {
        R5900Context ctx;
        uint32_t state = pattern * 0x9e3779b9u;
        auto* bytes = reinterpret_cast<unsigned char*>(&ctx);
        for (size_t i=0; i<sizeof(ctx); ++i) {
            state = state * 1664525u + 1013904223u;
            bytes[i] = static_cast<unsigned char>(state >> 24);
        }
        ctx.r[0] = _mm_setzero_si128();
        ctx.r[31] = _mm_set_epi32(pattern*0x1234567u,0x7fc00001u,0xfedcba98u,target);
        ctx.pc = entry;
        R5900Context expected;
        std::memcpy(&expected, &ctx, sizeof(ctx));
        expected.pc = target; // Original JR $ra followed by the original NOP.
        method(ram.data(), &ctx, nullptr);
        if (std::memcmp(&ctx, &expected, sizeof(ctx)) || ram != original_ram) {
            std::cerr << "Original return semantics differ for " << std::hex << entry << " -> " << target << '\n';
            return 1;
        }
        ++cases;
    }
    std::cout << cases << " actual translated-method cases passed: original return target, full CPU state and unchanged RAM.\n";
}
