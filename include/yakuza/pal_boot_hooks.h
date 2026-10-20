// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
class PS2Runtime;
namespace yakuza {
// Only for the SHA-256-verified PAL resident build running on PS2Runtime's
// native EE kernel services. This does not initialize or emulate a PS2 BIOS.
void install_pal_kernel_hooks(PS2Runtime& runtime);
void install_pal_sdk_hooks(PS2Runtime& runtime);
void install_boot_supplement(PS2Runtime& runtime);
}
