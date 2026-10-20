// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/pal_boot_hooks.h"
#include "ps2_runtime_macros.h"
#include <iostream>
#include <stdexcept>

namespace yakuza {
namespace {
void firmware_patch_installer(uint8_t*, R5900Context* context, PS2Runtime*) {
    std::cout << "[yakuza-kernel] SDK firmware patch installer at 0x" << std::hex << context->pc
              << " uses native kernel services" << std::dec << '\n';
    SET_GPR_S32(context, 2, 0);
    context->pc = GPR_U32(context, 31);
}
} // namespace

void install_pal_kernel_hooks(PS2Runtime& runtime) {
    // Observed in the original CRT initialization chain at 0x10f518:
    // 0x10f408 installs FindAddress/copy syscalls and searches firmware for the
    // kernel table. With no firmware image it loops forever at 0x10f490.
    // The other three routines copy MIPS patches to firmware kernel addresses
    // and install those handlers. PS2Runtime supplies the corresponding native
    // kernel services; executing firmware patch code would corrupt their setup.
    // Keep all other CRT initialization: libc semaphores, timers, top thread,
    // and the final scratch structure initialization are original guest code.
    for (uint32_t address : {0x10f408u, 0x10f9f8u, 0x10f640u, 0x10eb30u}) {
        if (!runtime.hasFunction(address) || !runtime.replaceFunction(address, firmware_patch_installer))
            throw std::runtime_error("PAL kernel hook does not match the generated resident map");
    }
}
} // namespace yakuza
