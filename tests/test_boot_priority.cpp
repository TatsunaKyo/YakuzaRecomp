// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic EE syscall regression; no original data or display required.
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_syscalls.h"
#include "runtime/ee_scheduler.h"
#include <iostream>
#include <stdexcept>

void check(bool value) { if (!value) throw std::runtime_error("EE priority syscall regression"); }
int main() {
    PS2Runtime runtime;
    check(runtime.memory().initialize());
    auto* memory = runtime.memory().getRDRAM();
    R5900Context context{};
    context.pc = 0x100008;
    auto& ee = runtime.eeScheduler();
    ee.bindMainContextForSyscall(context, memory);
    int previous = 0;
    check(ee.changePriority(0, 24, false, previous) == 0);

    SET_GPR_S32((&context), 4, 0); // Current guest thread.
    SET_GPR_S32((&context), 5, 1);
    ps2_syscalls::ChangeThreadPriority(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == 24 && ee.currentThread()->currentPriority == 1);
    SET_GPR_S32((&context), 5, GPR_S32((&context), 2));
    ps2_syscalls::ChangeThreadPriority(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == 1 && ee.currentThread()->currentPriority == 24);

    SET_GPR_S32((&context), 5, 8);
    ps2_syscalls::iChangeThreadPriority(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == 24 && ee.currentThread()->currentPriority == 8);
    SET_GPR_S32((&context), 5, GPR_S32((&context), 2));
    ps2_syscalls::iChangeThreadPriority(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == 8 && ee.currentThread()->currentPriority == 24);

    SET_GPR_S32((&context), 5, 0); // Invalid priority must retain its real error.
    ps2_syscalls::ChangeThreadPriority(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == -403 && ee.currentThread()->currentPriority == 24);
    SET_GPR_S32((&context), 4, 0x7fff);
    SET_GPR_S32((&context), 5, 8);
    ps2_syscalls::iChangeThreadPriority(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == -407 && ee.currentThread()->currentPriority == 24);
    std::cout << "Priority boost/restore returns prior values; interrupt-safe and error cases pass\n";
}
