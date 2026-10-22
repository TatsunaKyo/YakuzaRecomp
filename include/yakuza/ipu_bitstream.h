// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <deque>
#include <span>
#include <stdexcept>
#include <unordered_map>
#include <functional>
#include "yakuza/ipu_block.h"

namespace yakuza {
// A missing native device capability must not become an EE address exception.
class IpuError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
// EE IPU transport, MPEG symbols and BDEC macroblocks. IDEC, CSC and PACK
// remain explicitly unsupported.
class IpuBitstream {
public:
    using Registers = std::unordered_map<uint32_t, uint32_t>;
    using OutputWriter = std::function<void(uint32_t, std::span<const uint8_t, 16>)>;
    void write(uint32_t address, uint32_t value, Registers& io, std::span<const uint8_t> ram, const OutputWriter& output);
    uint32_t read(uint32_t address, Registers& io, std::span<const uint8_t> ram, const OutputWriter& output);
    void fifo(std::span<const uint8_t, 16> bytes, Registers& io, std::span<const uint8_t> ram, const OutputWriter& output);
    std::array<uint8_t, 16> output(Registers& io, std::span<const uint8_t> ram, const OutputWriter& writer);
    bool takeDmaCompletion();
    bool takeOutputDmaCompletion();
    struct Snapshot {
        uint32_t command, result, control, position, input_fifo, internal;
        bool busy;
        uint64_t cpu_quadwords, dma_quadwords;
        uint32_t input_chcr, input_madr, input_qwc, input_tadr, output_chcr, output_madr, output_qwc;
        std::array<uint64_t, 16> commands;
    };
    Snapshot snapshot() const;
private:
    friend class IpuBlockDecoder;
    using Quad = std::array<uint8_t, 16>;
    std::deque<Quad> fifo_, internal_;
    std::deque<Quad> output_fifo_;
    IpuBlockDecoder decoder_;
    std::array<uint8_t, 768> block_output_{};
    unsigned output_cursor_ = 0, pattern_ = 0;
    bool output_complete_ = false, start_code_ = false;
    std::array<uint8_t, 128> quant_{};
    std::array<uint8_t, 32> vq_{};
    std::array<uint16_t, 2> thresholds_{};
    unsigned position_ = 0, skip_ = 0, copied_ = 0, kind_ = 0;
    uint32_t command_ = 0, result_ = 0, control_ = 0;
    bool busy_ = false, error_ = false, dma_ = false, chain_ = false, chain_end_ = false, complete_ = false;
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
    void service(Registers& io, std::span<const uint8_t> ram, const OutputWriter& output);
    void pumpOutput(Registers& io, const OutputWriter& output);
    uint32_t controlValue() const;
};
IpuBitstream& ipuFor(const void* memory);
void releaseIpu(const void* memory);
}
