// SPDX-License-Identifier: GPL-3.0-or-later
// Register/bit ordering was cross-checked against PCSX2's documented IPU model;
// see THIRD_PARTY_NOTICES.md. This is independent of original game code.
#include "yakuza/ipu_bitstream.h"
#include <algorithm>
#include <cstring>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>

namespace yakuza {
namespace {
constexpr uint32_t dma = 0x1000b400, cmd = 0x10002000;
std::mutex devices_mutex;
std::map<const void*, IpuBitstream> devices;
std::span<const uint8_t> source(std::span<const uint8_t> ram, uint32_t address, unsigned bytes) {
    const uint32_t physical = address & 0x1fffffff;
    if (physical > ram.size() || bytes > ram.size() - physical)
        throw std::runtime_error("IPU DMA input is outside EE RAM");
    return ram.subspan(physical, bytes);
}
uint32_t le32(std::span<const uint8_t> data, unsigned offset) {
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) value |= uint32_t(data[offset+i]) << (i*8);
    return value;
}
}
IpuBitstream& ipuFor(const void* memory) {
    std::lock_guard lock(devices_mutex);
    return devices[memory];
}
void releaseIpu(const void* memory) {
    std::lock_guard lock(devices_mutex);
    devices.erase(memory);
}
void IpuBitstream::clearInput() {
    fifo_.clear(); internal_.clear(); position_ = 0;
}
void IpuBitstream::pump(Registers& io, std::span<const uint8_t> ram) {
    if (!dma_ || !(io[dma] & 0x100) || !(io[0x1000e000] & 1)) return;
    while (fifo_.size() < 8) {
        if (!io[dma+0x20]) {
            if (!chain_ || chain_end_) {
                dma_ = false; complete_ = true; io[dma] &= ~0x100u; break;
            }
            if (++tag_count_ > 100000) throw std::runtime_error("IPU DMA chain exceeds its tag budget");
            const auto tag = source(ram, next_tag_, 16);
            const uint32_t lo = le32(tag, 0), address = le32(tag, 4) & 0x7fffffff;
            const unsigned id = (lo >> 28) & 7, count = lo & 0xffff;
            const uint32_t after = next_tag_ + 16;
            switch (id) {
            case 0: io[dma+0x10] = address; next_tag_ = after; chain_end_ = true; break; // REFE
            case 1: io[dma+0x10] = after; next_tag_ = after + count*16; break; // CNT
            case 2: io[dma+0x10] = after; next_tag_ = address; break; // NEXT
            case 3: case 4: io[dma+0x10] = address; next_tag_ = after; break; // REF/REFS
            case 7: io[dma+0x10] = after; next_tag_ = after + count*16; chain_end_ = true; break;
            default: throw std::runtime_error("IPU DMA CALL/RET chains are not implemented");
            }
            if ((io[dma] & 0x80) && (lo & 0x80000000)) chain_end_ = true;
            io[dma] = (io[dma] & 0xffff) | (lo & 0xffff0000);
            io[dma+0x20] = count; io[dma+0x30] = next_tag_;
            if (!count) continue;
        }
        const auto bytes = source(ram, io[dma+0x10], 16);
        Quad quad; std::copy(bytes.begin(), bytes.end(), quad.begin()); fifo_.push_back(quad);
        ++dma_quadwords_;
        io[dma+0x10] += 16; --io[dma+0x20];
    }
    if (dma_ && !io[dma+0x20] && (!chain_ || chain_end_)) {
        dma_ = false; complete_ = true; io[dma] &= ~0x100u;
    }
}
bool IpuBitstream::ensure(unsigned bits, Registers& io, std::span<const uint8_t> ram) {
    pump(io, ram);
    while (internal_.size()*128 < position_ + bits) {
        if (fifo_.empty()) return false;
        internal_.push_back(fifo_.front()); fifo_.pop_front(); pump(io, ram);
    }
    return true;
}
void IpuBitstream::advance(unsigned bits) {
    position_ += bits;
    while (position_ >= 128) {
        position_ -= 128; internal_.pop_front();
    }
}
uint32_t IpuBitstream::peek(unsigned bits) const {
    uint32_t value = 0;
    for (unsigned i = 0; i < bits; ++i) {
        const unsigned bit = position_ + i;
        value = (value << 1) | ((internal_[bit/128][(bit%128)/8] >> (7-bit%8)) & 1);
    }
    return value;
}
void IpuBitstream::service(Registers& io, std::span<const uint8_t> ram) {
    registers_ = &io;
    pump(io, ram);
    if (!busy_) return;
    if (skip_) {
        if (!ensure(skip_, io, ram)) return;
        advance(skip_); skip_ = 0;
    }
    if (kind_ == 4) {
        if (!ensure(32, io, ram)) return;
        result_ = peek(32); busy_ = false;
    } else if (kind_ == 5 || kind_ == 6) {
        const unsigned count = kind_ == 5 ? 64 : 32;
        while (copied_ < count) {
            if (!ensure(8, io, ram)) return;
            const auto value = uint8_t(peek(8)); advance(8);
            if (kind_ == 5) quant_[copied_ + ((command_ & (1u << 27)) ? 64 : 0)] = value;
            else vq_[copied_] = value;
            ++copied_;
        }
        busy_ = false;
    }
    pump(io, ram);
}
void IpuBitstream::write(uint32_t address, uint32_t value, Registers& io, std::span<const uint8_t> ram) {
    if (address >= dma && address < dma + 0x100) {
        io[address] = value;
        if (address == dma) {
            dma_ = (value & 0x100) != 0;
            if (dma_) {
                const unsigned mode = (value >> 2) & 3;
                if (mode > 1 || !(value & 1) || (value & 0x40))
                    throw std::runtime_error("Unsupported IPU input DMA mode");
                chain_ = mode == 1; chain_end_ = false; tag_count_ = 0;
                next_tag_ = io[dma+0x30];
            }
        }
    } else if (address == cmd + 0x10) {
        control_ = value & 0x07f30000;
        if (value & (1u << 30)) {
            clearInput(); busy_ = false; result_ = 0; kind_ = 0; skip_ = copied_ = 0;
        }
    } else if (address == cmd) {
        kind_ = value >> 28; command_ = value;
        ++commands_[kind_];
        if (kind_ == 0) {
            clearInput(); position_ = value & 127; busy_ = false; skip_ = copied_ = 0;
        } else if (kind_ == 9) {
            thresholds_ = {uint16_t(value & 511), uint16_t((value >> 16) & 511)};
            busy_ = false;
        }
        else if (kind_ == 4 || kind_ == 5 || kind_ == 6) {
            skip_ = kind_ == 6 ? 0 : value & 63; copied_ = 0; busy_ = true;
        } else {
            std::ostringstream message; message << "IPU decode command not implemented: 0x" << std::hex << value;
            throw std::runtime_error(message.str());
        }
    }
    service(io, ram);
}
uint32_t IpuBitstream::read(uint32_t address, Registers& io, std::span<const uint8_t> ram) {
    service(io, ram);
    if (address >= dma && address < dma + 0x100) return io[address];
    const uint32_t busy = busy_ ? 0x80000000 : 0;
    switch (address - cmd) {
    case 0: if (kind_ != 4 && ensure(32, io, ram)) result_ = peek(32); return result_;
    case 4: return busy;
    case 0x10: return control_ | busy | uint32_t(fifo_.size());
    case 0x20: return (position_ & 127) | (uint32_t(fifo_.size()) << 8) | (uint32_t(internal_.size()) << 16);
    case 0x30: return ensure(32, io, ram) ? peek(32) : 0;
    case 0x34: return busy;
    default: return 0;
    }
}
void IpuBitstream::fifo(std::span<const uint8_t, 16> bytes, Registers& io, std::span<const uint8_t> ram) {
    service(io, ram);
    if (fifo_.size() == 8) throw std::runtime_error("IPU input FIFO overflow");
    Quad quad; std::copy(bytes.begin(), bytes.end(), quad.begin()); fifo_.push_back(quad);
    ++cpu_quadwords_;
    service(io, ram);
}
bool IpuBitstream::takeDmaCompletion() {
    const bool value = complete_; complete_ = false; return value;
}
IpuBitstream::Snapshot IpuBitstream::snapshot() const {
    const auto reg = [&](uint32_t address) {
        if (!registers_) return uint32_t(0);
        const auto found = registers_->find(address);
        return found == registers_->end() ? uint32_t(0) : found->second;
    };
    return {command_, result_, position_, uint32_t(fifo_.size()), uint32_t(internal_.size()), busy_,
            cpu_quadwords_, dma_quadwords_, reg(dma), reg(dma+0x10), reg(dma+0x20), reg(dma+0x30),
            reg(0x1000b000), reg(0x1000b010), reg(0x1000b020), commands_};
}
}
