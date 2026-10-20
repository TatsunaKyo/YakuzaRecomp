// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic scheduler regression; requires no original game or display.
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ee_scheduler.h"
#include <iostream>
#include <stdexcept>

namespace {
constexpr uint32_t entry = 0x100008, caller = 0x100100, stack = 0x1fff000;
unsigned calls = 0;
void recursive_yield(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    ++calls;
    SET_GPR_U32(context, 29, GPR_U32(context, 29) - 0x40);
    // Force a safe point immediately before the recursive call's entry. The
    // active outer frame must remain suspended, with PC at that recursive call.
    runtime->eeScheduler().postEvent(EeEvent{EeEventType::VBlankStart, 0, 0});
    SET_GPR_U32(context, 31, entry + 8);
    if (!runtime->dispatchGuestBranch(memory, context, entry, entry + 4, entry + 8,
            PS2Runtime::GuestBranchKind::DirectCall, "synthetic recursive JAL")) return;
    throw std::runtime_error("Recursive dispatch unexpectedly completed");
}
void explicit_return(uint8_t*, R5900Context* context, PS2Runtime*) {
    context->pc = GPR_U32(context, 31);
}
void check(bool value) { if (!value) throw std::runtime_error("Guest dispatch regression"); }
}
int main() {
    PS2Runtime runtime;
    check(runtime.memory().initialize());
    auto* memory = runtime.memory().getRDRAM();
    R5900Context context{};
    context.pc = entry;
    SET_GPR_U32((&context), 29, stack);
    SET_GPR_U32((&context), 31, caller);
    runtime.eeScheduler().reset(memory, context);
    check(runtime.replaceFunction(entry, recursive_yield));
    const bool completed = runtime.dispatchGuestBranch(memory, &context, entry, caller - 8, caller,
        PS2Runtime::GuestBranchKind::DirectCall, "synthetic caller");
    check(!completed && calls == 1 && context.pc == entry && GPR_U32((&context), 29) == stack - 0x40);

    context = R5900Context{};
    context.pc = entry;
    SET_GPR_U32((&context), 29, stack);
    SET_GPR_U32((&context), 31, caller);
    runtime.eeScheduler().reset(memory, context);
    check(runtime.replaceFunction(entry, explicit_return));
    check(runtime.dispatchGuestBranch(memory, &context, entry, caller - 8, caller,
        PS2Runtime::GuestBranchKind::DirectCall, "explicit return"));
    check(context.pc == caller && GPR_U32((&context), 29) == stack);
    std::cout << "Recursive yield retains PC/stack; explicit guest return completes the call\n";
}
