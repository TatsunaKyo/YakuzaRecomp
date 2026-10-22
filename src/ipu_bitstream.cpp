// SPDX-License-Identifier: GPL-3.0-or-later
// Register/bit ordering was cross-checked against PCSX2's documented IPU model;
// see THIRD_PARTY_NOTICES.md. This is independent of original game code.
#include "yakuza/ipu_bitstream.h"
#include "../third_party/pcsx2/mpeg2_vlc.h"
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
        throw IpuError("IPU DMA input is outside EE RAM");
    return ram.subspan(physical, bytes);
}
uint32_t le32(std::span<const uint8_t> data, unsigned offset) {
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) value |= uint32_t(data[offset+i]) << (i*8);
    return value;
}
// MPEG-1/2 macroblock_address_increment codewords, in increment order.
constexpr std::array<uint16_t, 33> mba_codes{1,3,2,3,2,3,2,7,6,11,10,9,8,7,6,
    23,22,21,20,19,18,35,34,33,32,31,30,29,28,27,26,25,24};
constexpr std::array<uint8_t, 33> mba_lengths{1,3,3,4,4,5,5,7,7,8,8,8,8,8,8,
    10,10,10,10,10,10,11,11,11,11,11,11,11,11,11,11,11,11};
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
            if (++tag_count_ > 100000) throw IpuError("IPU DMA chain exceeds its tag budget");
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
            default: throw IpuError("IPU DMA CALL/RET chains are not implemented");
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
void IpuBitstream::pumpOutput(Registers& io, const OutputWriter& output) {
    constexpr uint32_t from = 0x1000b000;
    if (!(io[from] & 0x100) || !(io[0x1000e000] & 1)) return;
    while (!output_fifo_.empty() && io[from+0x20]) {
        output(io[from+0x10], std::span<const uint8_t, 16>(output_fifo_.front()));
        output_fifo_.pop_front(); io[from+0x10] += 16; --io[from+0x20];
    }
    if (!io[from+0x20]) { io[from] &= ~0x100u; output_complete_ = true; }
}
void IpuBitstream::service(Registers& io, std::span<const uint8_t> ram, const OutputWriter& output) {
    registers_ = &io;
    pump(io, ram);
    pumpOutput(io, output);
    if (!busy_) return;
    if (skip_) {
        if (!ensure(skip_, io, ram)) return;
        advance(skip_); skip_ = 0;
    }
    if (kind_ == 2) {
        if (!copied_) {
            if (!decoder_.step(*this, io, ram)) return;
            if (decoder_.error()) { error_ = true; busy_ = false; return; }
            const auto& pixels = decoder_.samples();
            for (unsigned i = 0; i < pixels.size(); ++i) {
                block_output_[2*i] = uint8_t(pixels[i]);
                block_output_[2*i+1] = uint8_t(uint16_t(pixels[i]) >> 8);
            }
            pattern_ = decoder_.pattern(); output_cursor_ = 0; copied_ = 1;
        }
        if (copied_ == 1) {
            while (output_cursor_ < block_output_.size()) {
                pumpOutput(io, output);
                if (output_fifo_.size() == 8) return;
                Quad quad;
                std::copy_n(block_output_.begin()+output_cursor_, 16, quad.begin());
                output_fifo_.push_back(quad); output_cursor_ += 16;
            }
            pumpOutput(io, output); copied_ = 2;
        }
        if (copied_ == 2) {
            if (!ensure(8, io, ram)) return;
            if (peek(8) == 0) { advance((8-(position_ & 7)) & 7); copied_ = 3; }
            else copied_ = 4;
        }
        if (copied_ == 3) {
            while (true) {
                if (!ensure(24, io, ram)) return;
                const auto prefix = peek(24);
                if (prefix) { start_code_ = prefix == 1; error_ = !start_code_; break; }
                advance(8);
            }
            copied_ = 4;
        }
        if (!ensure(32, io, ram)) return;
        busy_ = false;
    } else if (kind_ == 3) {
        if (!copied_) {
            if (!ensure(32, io, ram)) return;
            const auto input = peek(32);
            result_ = 0;
            unsigned length = 0;
            const unsigned table = (command_ >> 26) & 3;
            if (table == 0) {
                for (unsigned i = 0; i < mba_codes.size(); ++i) {
                    if ((input >> (32-mba_lengths[i])) == mba_codes[i]) {
                        length = mba_lengths[i]; result_ = (length << 16) | (i+1); break;
                    }
                }
                if (!result_ && ((input >> 21) == 8 ||
                        ((input >> 21) == 15 && (control_ & (1u << 23))))) {
                    length = 11;
                    result_ = (length << 16) | ((input >> 21) == 8 ? 35 : 34);
                }
            } else if (table == 1) {
                unsigned picture = (control_ >> 24) & 7;
                if (!picture) picture = I_TYPE;
                const MBtab* entry = nullptr;
                if (picture == I_TYPE && (input >> 30)) entry = &MB_I[input >> 31];
                if (picture == P_TYPE && (input >> 26)) entry = &MB_P[input >> 27];
                if (picture == B_TYPE && (input >> 26)) entry = &MB_B[input >> 26];
                if (entry) {
                    length = entry->len; result_ = entry->modes;
                    if (picture == P_TYPE && (result_ & MACROBLOCK_MOTION_FORWARD)) result_ |= MC_FRAME;
                    if (picture == B_TYPE) result_ |= MC_FRAME | (length << 16);
                } else if (picture == D_TYPE && (input >> 31)) {
                    length = 1; result_ = MACROBLOCK_INTRA | (1u << 16);
                }
            } else if (table == 2) {
                if (input >> 31) { length = 1; result_ = 1u << 16; }
                else {
                    const unsigned word = input >> 16;
                    const MVtab* entry = nullptr;
                    if ((word & 0xf000) || (word & 0xfc00) == 0x0c00) entry = &MV_4[input >> 28];
                    else if ((input >> 22) >= 12) entry = &MV_10[input >> 22];
                    if (entry) {
                        const unsigned sign = (input >> (31-entry->len)) & 1;
                        const int delta = int(entry->delta) + 1;
                        result_ = uint32_t(sign ? -delta : delta) | (uint32_t(entry->len) << 16);
                        length = entry->len + 1;
                    }
                }
            } else {
                const auto& entry = DMV_2[input >> 30];
                length = entry.len; result_ = uint32_t(int32_t(entry.dmv)) | (length << 16);
            }
            error_ = result_ == 0;
            advance(length); copied_ = 1;
        }
        // VDEC also publishes a fresh TOP; wait if it needs more input.
        if (!ensure(32, io, ram)) return;
        busy_ = false;
    } else if (kind_ == 4) {
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
void IpuBitstream::write(uint32_t address, uint32_t value, Registers& io, std::span<const uint8_t> ram,
                         const OutputWriter& output) {
    if (address >= 0x1000b000 && address < 0x1000b100) {
        if (address == 0x1000b000 && (value & 0x100) && (value & 0xc))
            throw IpuError("IPU output DMA supports normal mode only");
        io[address] = value;
    } else if (address >= dma && address < dma + 0x100) {
        io[address] = value;
        if (address == dma) {
            dma_ = (value & 0x100) != 0;
            if (dma_) {
                const unsigned mode = (value >> 2) & 3;
                if (mode > 1 || !(value & 1) || (value & 0x40))
                    throw IpuError("Unsupported IPU input DMA mode");
                chain_ = mode == 1; chain_end_ = false; tag_count_ = 0;
                next_tag_ = io[dma+0x30];
            }
        }
    } else if (address == cmd + 0x10) {
        control_ = value & 0x07f30000;
        if (value & (1u << 30)) {
            clearInput(); output_fifo_.clear(); decoder_ = IpuBlockDecoder{};
            busy_ = error_ = start_code_ = false; pattern_ = 0; result_ = 0; kind_ = 0; skip_ = copied_ = 0;
        }
    } else if (address == cmd) {
        kind_ = value >> 28; command_ = value;
        ++commands_[kind_];
        error_ = start_code_ = false;
        if (kind_ == 0) {
            clearInput(); position_ = value & 127; busy_ = false; skip_ = copied_ = 0;
        } else if (kind_ == 2) {
            decoder_.start(value, control_); skip_ = value & 63; copied_ = 0; busy_ = true;
        } else if (kind_ == 9) {
            thresholds_ = {uint16_t(value & 511), uint16_t((value >> 16) & 511)};
            busy_ = false;
        }
        else if (kind_ == 3 || kind_ == 4 || kind_ == 5 || kind_ == 6) {
            skip_ = kind_ == 6 ? 0 : value & 63; copied_ = 0; busy_ = true;
        } else {
            std::ostringstream message; message << "IPU decode command not implemented: 0x" << std::hex << value;
            throw IpuError(message.str());
        }
    }
    service(io, ram, output);
}
uint32_t IpuBitstream::read(uint32_t address, Registers& io, std::span<const uint8_t> ram,
                            const OutputWriter& output) {
    service(io, ram, output);
    if ((address >= dma && address < dma + 0x100) ||
            (address >= 0x1000b000 && address < 0x1000b100)) return io[address];
    const uint32_t busy = busy_ ? 0x80000000 : 0;
    switch (address - cmd) {
    case 0: if (kind_ != 3 && kind_ != 4 && ensure(32, io, ram)) result_ = peek(32); return result_;
    case 4: return busy;
    case 0x10: return controlValue();
    case 0x20: return (position_ & 127) | (uint32_t(fifo_.size()) << 8) | (uint32_t(internal_.size()) << 16);
    case 0x30: return ensure(32, io, ram) ? peek(32) : 0;
    case 0x34: return busy;
    default: return 0;
    }
}
void IpuBitstream::fifo(std::span<const uint8_t, 16> bytes, Registers& io, std::span<const uint8_t> ram,
                         const OutputWriter& output) {
    service(io, ram, output);
    if (fifo_.size() == 8) throw IpuError("IPU input FIFO overflow");
    Quad quad; std::copy(bytes.begin(), bytes.end(), quad.begin()); fifo_.push_back(quad);
    ++cpu_quadwords_;
    service(io, ram, output);
}
std::array<uint8_t, 16> IpuBitstream::output(Registers& io, std::span<const uint8_t> ram,
                                           const OutputWriter& writer) {
    service(io, ram, writer);
    if (output_fifo_.empty()) throw IpuError("IPU output FIFO is empty");
    const auto quad = output_fifo_.front(); output_fifo_.pop_front();
    service(io, ram, writer); return quad;
}
bool IpuBitstream::takeDmaCompletion() {
    const bool value = complete_; complete_ = false; return value;
}
bool IpuBitstream::takeOutputDmaCompletion() {
    const bool value = output_complete_; output_complete_ = false; return value;
}
uint32_t IpuBitstream::controlValue() const {
    return control_ | (error_ ? 0x4000u : 0) | (start_code_ ? 0x8000u : 0) |
        (busy_ ? 0x80000000u : 0) | (pattern_ << 8) | uint32_t(output_fifo_.size() << 4) | uint32_t(fifo_.size());
}
IpuBitstream::Snapshot IpuBitstream::snapshot() const {
    const auto reg = [&](uint32_t address) {
        if (!registers_) return uint32_t(0);
        const auto found = registers_->find(address);
        return found == registers_->end() ? uint32_t(0) : found->second;
    };
    return {command_, result_, controlValue(),
            position_, uint32_t(fifo_.size()), uint32_t(internal_.size()), busy_,
            cpu_quadwords_, dma_quadwords_, reg(dma), reg(dma+0x10), reg(dma+0x20), reg(dma+0x30),
            reg(0x1000b000), reg(0x1000b010), reg(0x1000b020), commands_};
}
}
