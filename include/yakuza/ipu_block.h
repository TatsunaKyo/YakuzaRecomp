// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <span>
#include <unordered_map>

namespace yakuza {
class IpuBitstream;
class IpuBlockDecoder {
public:
    void start(uint32_t command, uint32_t control);
    bool step(IpuBitstream& input, std::unordered_map<uint32_t, uint32_t>& io, std::span<const uint8_t> ram);
    const std::array<int16_t, 384>& samples() const { return samples_; }
    bool error() const { return error_; }
    unsigned pattern() const { return pattern_; }
private:
    std::array<int16_t, 384> samples_{};
    std::array<int16_t, 64> coefficients_{};
    std::array<int16_t, 3> predictors_{128,128,128};
    uint32_t command_ = 0, control_ = 0;
    unsigned block_ = 0, coefficient_ = 0, pattern_ = 0, scale_ = 0;
    bool intra_ = false, dc_ready_ = false, pattern_ready_ = false, error_ = false;
    void finishBlock();
    void nextBlock();
};
}
