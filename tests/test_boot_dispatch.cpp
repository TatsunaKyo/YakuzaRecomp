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
unsigned vifPhase = 0, vifInterrupts = 0;
constexpr uint32_t vifHandler = entry + 0x200;
void vif_check(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
void vif_irq_handler(uint8_t* memory, R5900Context* context, PS2Runtime* runtime) {
    vif_check(GPR_U32(context, 4) == 5, "VIF1 handler received the wrong INTC cause");
    ++vifInterrupts;
    vif_check(runtime->memory().vif1_regs.mark == vifInterrupts,
              "VIF1 handler lost the MARK belonging to its flush barrier");
    runtime->Store32(memory, context, 0x10003c10, 8); // Original-style STC acknowledgement.
    context->pc = GPR_U32(context, 31);
}
void vif_driver(uint8_t*, R5900Context* context, PS2Runtime* runtime) {
    auto& memory = runtime->memory();
    if (vifPhase == 0) {
        const uint32_t stream[] = {0x07000001, 0x90000000, 0x07000002,
                                   0x91000000, 0x07000003};
        memory.processVIF1Data(reinterpret_cast<const uint8_t*>(stream), sizeof(stream));
        vifPhase = 1;
        return;
    }
    if (vifPhase == 1) {
        vif_check(vifInterrupts == 0 && memory.vif1_regs.mark == 1 &&
                  (memory.read32(0x1000f000) & (1u << 5)),
                  "Disabled VIF1 cause lost its pending barrier");
        runtime->eeScheduler().setIrqCauseEnabled(false, 5, true);
        vifPhase = 2;
        return;
    }
    vif_check(vifInterrupts == 2 && memory.vif1_regs.mark == 3 &&
              !(memory.vif1_regs.stat & 0xc00u),
              "Queued EE VIF1 handlers did not acknowledge and resume both barriers");
    context->pc = 0;
    runtime->eeScheduler().requestStop();
}
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

    PS2Runtime interruptRuntime;
    check(interruptRuntime.memory().initialize());
    R5900Context irqContext{};
    irqContext.pc = entry;
    SET_GPR_U32((&irqContext), 29, stack);
    interruptRuntime.eeScheduler().reset(interruptRuntime.memory().getRDRAM(), irqContext);
    check(interruptRuntime.replaceFunction(entry, vif_driver));
    check(interruptRuntime.registerFunction(vifHandler, vif_irq_handler));
    check(interruptRuntime.eeScheduler().addIrqHandler(false, 5, vifHandler, false, 0, 0, stack) > 0);
    interruptRuntime.eeScheduler().setIrqCauseEnabled(false, 5, false);
    interruptRuntime.eeScheduler().run();
    std::cout << "Recursive yield retains PC/stack; explicit guest return completes the call\n";
}
