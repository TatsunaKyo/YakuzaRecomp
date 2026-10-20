// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <optional>
#include <span>

namespace yakuza {
struct DbcPadPacket {
    std::array<uint8_t, 28> state{};
    std::array<uint8_t, 32> capabilities{};
};
// Convert a connected native PS2-format sample to the PAL device-bus ABI.
// Pressure buttons and rumble are not advertised by this adapter.
std::optional<DbcPadPacket> make_dbc_pad_packet(std::span<const uint8_t> sample);
}
