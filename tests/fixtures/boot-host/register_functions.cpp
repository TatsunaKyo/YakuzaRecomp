// Synthetic registration shape for testing the public host build without assets.
#include "ps2_runtime.h"
#include "ps2_recompiled_functions.h"
extern const uint32_t g_ps2RecompiledFunctionTableBase = 0x100008u;
extern const uint32_t g_ps2RecompiledFunctionTableEnd = 0x6ef500u;
extern const uint32_t g_ps2RecompiledFunctionTableSlotCount = 1555774u;
PS2Runtime::RecompiledFunction g_ps2RecompiledFunctionTable[1555774u] = {};
namespace {
struct Initializer {
    Initializer() { g_ps2RecompiledFunctionTable[0] = synthetic_entry; }
} initializer;
}
