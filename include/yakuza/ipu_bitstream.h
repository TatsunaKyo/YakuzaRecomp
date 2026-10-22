// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <deque>
#include <span>
#include <unordered_map>

namespace yakuza {
// EE IPU input transport and fixed-length bit operations. Compressed-picture
// and variable-length decode commands remain explicitly unsupported.
class IpuBitstream {
public:
    using Registers = std::unordered_map<uint32_t, uint32_t>;
    void write(uint32_t address, uint32_t value, Registers& io, std::span<const uint8_t> ram);
    uint32_t read(uint32_t address, Registers& io, std::span<const uint8_t> ram);
    void fifo(std::span<const uint8_t, 16> bytes, Registers& io, std::span<const uint8_t> ram);
    bool takeDmaCompletion();
    struct Snapshot {
        uint32_t command, result, position, input_fifo, internal;
        bool busy;
        uint64_t cpu_quadwords, dma_quadwords;
        uint32_t input_chcr, input_madr, input_qwc, input_tadr, output_chcr, output_madr, output_qwc;
        std::array<uint64_t, 16> commands;
    };
    Snapshot snapshot() const;
private:
    using Quad = std::array<uint8_t, 16>;
    std::deque<Quad> fifo_, internal_;
    std::array<uint8_t, 128> quant_{};
    std::array<uint8_t, 32> vq_{};
    std::array<uint16_t, 2> thresholds_{};
    unsigned position_ = 0, skip_ = 0, copied_ = 0, kind_ = 0;
    uint32_t command_ = 0, result_ = 0, control_ = 0;
    bool busy_ = false, dma_ = false, chain_ = false, chain_end_ = false, complete_ = false;
    uint32_t next_tag_ = 0;
    unsigned tag_count_ = 0;
    Registers* registers_ = nullptr;
    uint64_t cpu_quadwords_ = 0, dma_quadwords_ = 0;
    std::array<uint64_t, 16> commands_{};
    void clearInput();
    void pump(Registers& io, std::span<const uint8_t> ram);
    bool ensure(unsigned bits, Registers& io, std::span<const uint8_t> ram);
    void advance(unsigned bits);
    uint32_t peek(unsigned bits) const;
    void service(Registers& io, std::span<const uint8_t> ram);
};
IpuBitstream& ipuFor(const void* memory);
void releaseIpu(const void* memory);
}
