// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
struct R5900Context;
class GS;
namespace yakuza {
// Evaluate a verified upper instruction with the runtime's VU0 arithmetic and
// flag pipeline. Used at observed sites whose following NOPs drain that pipeline.
void vu0UpperWithFlags(R5900Context& context, GS& gs, uint32_t instruction);
}
