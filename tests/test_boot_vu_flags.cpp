// SPDX-License-Identifier: GPL-3.0-or-later
// Golden architectural cases for a discarded VU0 subtraction and its flags.
#include "ps2_runtime.h"
#include "yakuza/vu0_macro.hpp"
#include <array>
#include <bit>
#include <cfenv>
#include <cstring>
#include <iostream>
#include <stdexcept>

void synthetic_vsub_xy_zero(R5900Context*, PS2Runtime*);
void check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
float bits(uint32_t value) { return std::bit_cast<float>(value); }
int main() {
    PS2Runtime runtime;
    struct Case { float ax, ay, bx, by; uint32_t mac, current; };
    const std::array cases{
        Case{3, 1, 1, 2, 0x0040, 0x2}, // Positive X, negative Y.
        Case{1, 3, 2, 1, 0x0080, 0x2}, // Negative X, positive Y.
        Case{1, 2, 1, 2, 0x000c, 0x1}, // Both zero.
        Case{-0.f, 0.f, 0.f, -0.f, 0x008c, 0x3}, // Signed zero.
        Case{bits(0x00800001), bits(0x00800000), bits(0x00800000), bits(0x00800001), 0x0c4c, 0x7},
        Case{bits(0x7f7fffff), -bits(0x7f7fffff), -bits(0x7f7fffff), bits(0x7f7fffff), 0xc040, 0xa},
    };
    for (const auto& test : cases) {
        R5900Context ctx;
        ctx.vu0_vf[0] = _mm_set_ps(1.f, 0.f, 0.f, 0.f);
        ctx.vu0_vf[5] = _mm_set_ps(123.f, 456.f, test.ay, test.ax);
        ctx.vu0_vf[4] = _mm_set_ps(-789.f, -321.f, test.by, test.bx);
        const __m128 left = ctx.vu0_vf[5], right = ctx.vu0_vf[4];
        ctx.vu0_mac_flags = 0xffff; // Masked-off Z/W flag groups must clear.
        ctx.vu0_status = 0x830; // Preserve D/I and an existing sticky flag.
        synthetic_vsub_xy_zero(&ctx, &runtime);
        alignas(16) std::array<uint32_t,4> vf0;
        _mm_store_si128(reinterpret_cast<__m128i*>(vf0.data()), _mm_castps_si128(ctx.vu0_vf[0]));
        check(vf0 == std::array<uint32_t,4>{0,0,0,0x3f800000}, "VSUB targeting VF0 overwrote its hardware constant");
        check(ctx.vu0_mac_flags == test.mac, "VSUB did not publish the real XY MAC flags");
        check(ctx.vu0_status == (0x830 | test.current | (test.current << 6)), "VSUB lost current, sticky or D/I status flags");
        check(std::memcmp(&left, &ctx.vu0_vf[5], 16) == 0 && std::memcmp(&right, &ctx.vu0_vf[4], 16) == 0,
              "Discarded VSUB changed an input register");
    }
    R5900Context masked;
    masked.vu0_vf[0] = _mm_set_ps(1.f,0.f,0.f,0.f);
    masked.vu0_vf[1] = _mm_set_ps(11.f,0.f,-3.f,2.f);
    masked.vu0_vf[2] = _mm_set_ps(5.f,9.f,2.f,4.f);
    masked.vu0_vf[3] = _mm_set_ps(93.f,92.f,91.f,90.f);
    masked.vu0_status = 0x30;
    yakuza::vu0UpperWithFlags(masked,runtime.gs(),0x01c208eau); // VMUL.xyz VF3,VF1,VF2.
    alignas(16) std::array<float,4> output;
    _mm_store_ps(output.data(),masked.vu0_vf[3]);
    check(output == std::array<float,4>{8,-6,0,93}, "Masked VMUL lost a result or changed W");
    check(masked.vu0_mac_flags==0x42 && masked.vu0_status==0xf3, "Masked VMUL flags differ from the golden result");
    masked.vu0_acc = _mm_set_ps(40.f,30.f,20.f,10.f);
    masked.vu0_vf[1] = _mm_set_ps(0.f,0.f,3.f,2.f);
    masked.vu0_status = 0x30;
    yakuza::vu0UpperWithFlags(masked,runtime.gs(),0x018209bcu); // VMULAX.xy ACC,VF1,VF2x.
    _mm_store_ps(output.data(),masked.vu0_acc);
    check(output == std::array<float,4>{8,12,30,40}, "VMULAX lost its accumulator or mask semantics");
    yakuza::vu0UpperWithFlags(masked,runtime.gs(),0x018208bcu); // VMADDAX.xy ACC,VF1,VF2x.
    _mm_store_ps(output.data(),masked.vu0_acc);
    check(output == std::array<float,4>{16,24,30,40}, "VMADDAX lost its input accumulator");
    yakuza::vu0UpperWithFlags(masked,runtime.gs(),0x018208cfu); // VMSUBW.xy VF3,VF1,VF2w.
    _mm_store_ps(output.data(),masked.vu0_vf[3]);
    check(output[0]==6 && output[1]==9 && output[2]==0 && output[3]==93,
          "VMSUBW lost its product, accumulator or mask semantics");
    const int rounding = std::fegetround();
    check(std::fesetround(FE_UPWARD) == 0, "Cannot set host rounding for isolation check");
    R5900Context ctx;
    ctx.vu0_vf[0] = _mm_set_ps(1.f,0.f,0.f,0.f);
    synthetic_vsub_xy_zero(&ctx, &runtime);
    check(std::fegetround() == FE_UPWARD, "VU0 evaluator changed the host rounding mode");
    check(std::fesetround(rounding) == 0, "Cannot restore host rounding");
    std::cout << "Discarded VSUB preserves VF0 and operands; golden XY MAC/status and host rounding checks pass\n";
}
