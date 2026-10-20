// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/native_pad.h"
#include <algorithm>

namespace yakuza {
std::optional<DbcPadPacket> make_dbc_pad_packet(std::span<const uint8_t> sample) {
    if (sample.size() != 32 || sample[0] != 1 || (sample[1] != 0x41 && sample[1] != 0x73))
        return std::nullopt;
    DbcPadPacket packet;
    // Both interfaces use active-low buttons followed by RX, RY, LX, LY.
    packet.state[0] = sample[2];
    packet.state[1] = sample[3];
    const bool analog = sample[1] == 0x73;
    if (analog) std::copy_n(sample.begin() + 4, 4, packet.state.begin() + 2);
    else std::fill_n(packet.state.begin() + 2, 4, uint8_t{0x80});
    // Capability bits 0..15 are buttons, 16..19 are the four analog axes.
    packet.capabilities[0] = packet.capabilities[1] = 0xff;
    packet.capabilities[2] = analog ? 0x0f : 0;
    return packet;
}
}
