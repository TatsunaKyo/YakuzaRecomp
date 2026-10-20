// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/native_pad.h"
#include <algorithm>
#include <iostream>
#include <stdexcept>

void check(bool condition) { if (!condition) throw std::runtime_error("Native controller packet regression"); }
int main() {
    std::array<uint8_t, 32> sample{};
    sample[0] = 1; sample[1] = 0x73;
    sample[2] = 0xef; sample[3] = 0xbf; // Up and Cross held; other buttons released.
    sample[4] = 0; sample[5] = 255; sample[6] = 128; sample[7] = 64;
    std::fill(sample.begin() + 8, sample.end(), uint8_t{0xcc});
    auto packet = yakuza::make_dbc_pad_packet(sample);
    check(packet.has_value());
    check(packet->state[0] == 0xef && packet->state[1] == 0xbf);
    check(packet->state[2] == 0 && packet->state[3] == 255 && packet->state[4] == 128 && packet->state[5] == 64);
    check(std::all_of(packet->state.begin() + 6, packet->state.end(), [](uint8_t b) { return b == 0; }));
    check(packet->capabilities[0] == 255 && packet->capabilities[1] == 255 && packet->capabilities[2] == 15);
    check(std::all_of(packet->capabilities.begin() + 3, packet->capabilities.end(), [](uint8_t b) { return b == 0; }));
    sample[1] = 0x41; sample[2] = sample[3] = 0xff;
    packet = yakuza::make_dbc_pad_packet(sample);
    check(packet && packet->state[0] == 255 && packet->state[1] == 255 && packet->capabilities[2] == 0);
    check(std::all_of(packet->state.begin() + 2, packet->state.begin() + 6, [](uint8_t b) { return b == 128; }));
    sample[0] = 0;
    check(!yakuza::make_dbc_pad_packet(sample));
    sample[0] = 1; sample[1] = 0xff;
    check(!yakuza::make_dbc_pad_packet(sample));
    check(!yakuza::make_dbc_pad_packet(std::span(sample).first(31)));
    std::cout << "Controller press/release, axes, capability and disconnected-input checks passed\n";
}
