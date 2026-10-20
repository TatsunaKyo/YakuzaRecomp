// Synthetic registration shape for testing the public host build without assets.
#include "ps2_runtime.h"
#include "ps2_recompiled_functions.h"
extern const uint32_t g_ps2RecompiledFunctionTableBase = 0x100008u;
extern const uint32_t g_ps2RecompiledFunctionTableEnd = 0x5918a4u;
extern const uint32_t g_ps2RecompiledFunctionTableSlotCount = 1197607u;
PS2Runtime::RecompiledFunction g_ps2RecompiledFunctionTable[1197607u] = {};
namespace {
struct Initializer {
    Initializer() { g_ps2RecompiledFunctionTable[0] = synthetic_entry; }
} initializer;
}
