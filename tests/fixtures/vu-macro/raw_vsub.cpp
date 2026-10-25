// Synthetic pinned-emitter shape for VSUB.xy VF0,VF5,VF4; no game code or data.
#include "ps2_runtime_macros.h"
#include "ps2_runtime.h"

void synthetic_vsub_xy_zero(R5900Context* ctx, PS2Runtime* runtime) {
    (void)runtime;
    { __m128 res = PS2_VSUB(ctx->vu0_vf[5], ctx->vu0_vf[4]); __m128i mask = _mm_set_epi32(0, 0, -1, -1); ctx->vu0_vf[0] = PS2_VBLEND(ctx->vu0_vf[0], res, _mm_castsi128_ps(mask)); }
}
