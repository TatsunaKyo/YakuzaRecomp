// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic EE thread startup and resume/wakeup regression; no original assets or display.
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
    context.vu0_vf[0] = _mm_set_ps(1.f, 0.f, 0.f, 0.f);
    context.pc = 0x100008;
    auto& ee = runtime.eeScheduler();
    ee.bindMainContextForSyscall(context, memory);
    const int id = ee.createThread(EeThreadCreateParams{0, 0x100100, 0x20000, 0x1000, 0, 26, 0});
    check(id > 1 && ee.startThread(id, 0, context, false) == 0, "Worker did not start");
    alignas(16) float vf0[4];
    _mm_store_ps(vf0, ee.thread(id)->context.vu0_vf[0]);
    check(vf0[0] == 0.f && vf0[1] == 0.f && vf0[2] == 0.f && vf0[3] == 1.f,
          "Started EE thread lost the hardware VF0 constant (0,0,0,1)");
    check(ee.suspendThread(id, false) == 0, "Worker did not suspend");
    SET_GPR_S32((&context), 4, id);
    ps2_syscalls::ResumeThread(memory, &context, &runtime);
    // CRI compares the result with the target ID before issuing WakeupThread.
    // A zero return resumes the thread but silently skips that notification.
    if (GPR_S32((&context), 2) == id)
        ps2_syscalls::WakeupThread(memory, &context, &runtime);
    check(ee.thread(id)->status == EeThreadStatus::Ready && ee.thread(id)->wakeupCount == 1,
          "Successful resume skipped the caller's ID-guarded wakeup");
    check(GPR_S32((&context), 2) == id,
          "Successful wakeup lost the target ID required to acknowledge the notification");

    SET_GPR_S32((&context), 4, id);
    runtime.handleSyscall(memory, &context, uint32_t(-0x34));
    check(GPR_S32((&context), 2) == id && ee.thread(id)->wakeupCount == 2,
          "Interrupt-safe wakeup lost the thread ID or queued notification");
    SET_GPR_S32((&context), 4, 0x7fff);
    ps2_syscalls::WakeupThread(memory, &context, &runtime);
    check(GPR_S32((&context), 2) == -407, "Unknown-thread wakeup lost its real error");
    SET_GPR_S32((&context), 4, 0);
    ps2_syscalls::WakeupThread(memory, &context, &runtime);
    check(GPR_S32((&context), 2) < 0, "Illegal-thread wakeup reported success");

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
    uint32_t owned_stack = 0;
    check(ee.terminateThread(id, owned_stack, false) == 0, "Worker did not terminate for restart");
    check(ee.startThread(id, 0, context, false) == 0, "Worker did not restart");
    _mm_store_ps(vf0, ee.thread(id)->context.vu0_vf[0]);
    check(vf0[0] == 0.f && vf0[1] == 0.f && vf0[2] == 0.f && vf0[3] == 1.f,
          "Restarted EE thread lost the hardware VF0 constant (0,0,0,1)");
    std::cout << "Resume and wakeup return the real thread ID and preserve notifications and errors\n";
}
