// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic EE resume/wakeup ABI regression; no original assets or display.
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_syscalls.h"
#include "runtime/ee_scheduler.h"
#include <iostream>
#include <stdexcept>

void check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
int main() {
    PS2Runtime runtime;
    check(runtime.memory().initialize(), "Memory initialization failed");
    auto* memory = runtime.memory().getRDRAM();
    R5900Context context{};
    context.pc = 0x100008;
    auto& ee = runtime.eeScheduler();
    ee.bindMainContextForSyscall(context, memory);
    const int id = ee.createThread(EeThreadCreateParams{0, 0x100100, 0x20000, 0x1000, 0, 26, 0});
    check(id > 1 && ee.startThread(id, 0, context, false) == 0, "Worker did not start");
    check(ee.suspendThread(id, false) == 0, "Worker did not suspend");
    SET_GPR_S32((&context), 4, id);
    ps2_syscalls::ResumeThread(memory, &context, &runtime);
    // CRI compares the result with the target ID before issuing WakeupThread.
    // A zero return resumes the thread but silently skips that notification.
    if (GPR_S32((&context), 2) == id)
        ps2_syscalls::WakeupThread(memory, &context, &runtime);
    check(ee.thread(id)->status == EeThreadStatus::Ready && ee.thread(id)->wakeupCount == 1,
          "Successful resume skipped the caller's ID-guarded wakeup");

    check(ee.suspendThread(id, false) == 0, "Worker did not suspend again");
    SET_GPR_S32((&context), 4, id);
    runtime.handleSyscall(memory, &context, uint32_t(-0x3a));
    check(GPR_S32((&context), 2) == id && ee.thread(id)->status == EeThreadStatus::Ready,
          "Interrupt-safe numeric resume lost the thread ID");
    ps2_syscalls::ResumeThread(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == -415, "Unsuspended-thread resume lost its real error");
    SET_GPR_S32((&context), 4, 0x7fff);
    ps2_syscalls::ResumeThread(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == -407, "Unknown-thread resume lost its real error");
    std::cout << "Resume returns the real thread ID, permits the guarded wakeup and preserves errors\n";
}
