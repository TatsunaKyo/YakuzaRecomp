// Build fixture only. This function cannot run the original game.
#include "ps2_runtime.h"
void synthetic_entry(uint8_t*, R5900Context* context, PS2Runtime*) {
    context->pc = 0;
}
