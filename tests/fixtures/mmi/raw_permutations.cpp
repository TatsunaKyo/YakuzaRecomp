// Original-free shapes emitted by the pinned recompiler for R5900 MMI words.
#include "ps2_runtime_macros.h"
#include "ps2_runtime.h"

void synthetic_emitted_mmi(R5900Context* ctx) {
    // 0x100008: 0x70084e89  pexeh $t1, $t0
    SET_GPR_VEC(ctx, 9, _mm_shufflelo_epi16(_mm_shufflehi_epi16(GPR_VEC(ctx, 8), _MM_SHUFFLE(2,3,0,1)), _MM_SHUFFLE(2,3,0,1)));
    // 0x10000c: 0x700a5fc9  prot3w $t3, $t2
    SET_GPR_VEC(ctx, 11, _mm_shuffle_epi32(GPR_VEC(ctx, 10), _MM_SHUFFLE(0,3,2,1)));
    // 0x100010: 0x700c6689  pexeh $t4, $t4
    SET_GPR_VEC(ctx, 12, _mm_shufflelo_epi16(_mm_shufflehi_epi16(GPR_VEC(ctx, 12), _MM_SHUFFLE(2,3,0,1)), _MM_SHUFFLE(2,3,0,1)));
    // 0x100014: 0x700d6fc9  prot3w $t5, $t5
    SET_GPR_VEC(ctx, 13, _mm_shuffle_epi32(GPR_VEC(ctx, 13), _MM_SHUFFLE(0,3,2,1)));
}
