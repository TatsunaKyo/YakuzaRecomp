// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <functional>
#include <span>
#include <unordered_map>
namespace yakuza {
using ScratchpadWriter = std::function<void(uint32_t, std::span<const uint8_t,16>)>;
void runScratchpadSourceChain(uint32_t chcr, std::unordered_map<uint32_t,uint32_t>& io,
    std::span<const uint8_t> ram, std::span<const uint8_t> scratch, const ScratchpadWriter& write);
}
