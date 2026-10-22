// SPDX-License-Identifier: GPL-3.0-or-later
// Native MPEG block transport/decoder. VLC and IDCT sources retain PCSX2 and
// libmpeg2 notices in third_party/pcsx2; see THIRD_PARTY_NOTICES.md.
#include "yakuza/ipu_block.h"
#include "yakuza/ipu_bitstream.h"
#include "../third_party/pcsx2/mpeg2_vlc.h"
#include "../third_party/pcsx2/ipu_idct.h"
#include <algorithm>
#include <cstdlib>

namespace yakuza {
namespace {
constexpr std::array<unsigned, 64> normal_scan{
 0,1,8,16,9,2,3,10,17,24,32,25,18,11,4,5,12,19,26,33,40,48,41,34,27,20,13,6,7,14,21,28,
 35,42,49,56,57,50,43,36,29,22,15,23,30,37,44,51,58,59,52,45,38,31,39,46,53,60,61,54,47,55,62,63};
constexpr std::array<unsigned, 64> alternate_scan{
 0,8,16,24,1,9,2,10,17,25,32,40,48,56,57,49,41,33,26,18,3,11,4,12,19,27,34,42,50,58,35,43,
 51,59,20,28,5,13,6,14,21,29,36,44,52,60,37,45,53,61,22,30,7,15,23,31,38,46,54,62,39,47,55,63};
constexpr std::array<unsigned, 32> nonlinear{0,1,2,3,4,5,6,7,8,10,12,14,16,18,20,22,
 24,28,32,36,40,44,48,52,56,64,72,80,88,96,104,112};
unsigned permute(unsigned position) { return ((position & 0x36) >> 1) | ((position & 9) << 2); }
int signedBits(uint32_t value, unsigned bits) {
    const auto sign = 1u << (bits-1);
    return int((value ^ sign) - sign);
}
const DCTtab* symbol(unsigned code, bool alternate, bool first) {
    if (code >= 16384 && !alternate) return &(first ? DCT.first : DCT.next)[(code >> 12)-4];
    if (code >= 1024) return alternate ? &DCT.tab0a[(code >> 8)-4] : &DCT.tab0[(code >> 8)-4];
    if (code >= 512) return alternate ? &DCT.tab1a[(code >> 6)-8] : &DCT.tab1[(code >> 6)-8];
    if (code >= 256) return &DCT.tab2[(code >> 4)-16];
    if (code >= 128) return &DCT.tab3[(code >> 3)-16];
    if (code >= 64) return &DCT.tab4[(code >> 2)-16];
    if (code >= 32) return &DCT.tab5[(code >> 1)-16];
    if (code >= 16) return &DCT.tab6[code-16];
    return nullptr;
}
}
void IpuBlockDecoder::start(uint32_t command, uint32_t control) {
    command_ = command; control_ = control; block_ = 0; error_ = false;
    intra_ = (command & (1u << 27)) != 0;
    coefficient_ = intra_ ? 1 : 0; pattern_ = intra_ ? 63 : 0;
    pattern_ready_ = intra_; dc_ready_ = false;
    samples_.fill(0); coefficients_.fill(0);
    const unsigned qsc = (command >> 16) & 31;
    scale_ = control & (1u << 22) ? nonlinear[qsc] : qsc * 2;
    if (command & (1u << 26)) predictors_.fill(int16_t(128u << ((control >> 16) & 3)));
}
void IpuBlockDecoder::nextBlock() {
    ++block_; coefficients_.fill(0); coefficient_ = intra_ ? 1 : 0; dc_ready_ = false;
}
void IpuBlockDecoder::finishBlock() {
    ipu_math::inverseDct(coefficients_);
    const bool field = (command_ & (1u << 25)) != 0;
    unsigned offset, stride;
    if (block_ < 4) {
        stride = field ? 32 : 16;
        offset = (block_ & 1) * 8 + (block_ >= 2 ? (field ? 16 : 128) : 0);
    } else { stride = 8; offset = block_ == 4 ? 256 : 320; }
    for (unsigned y = 0; y < 8; ++y) for (unsigned x = 0; x < 8; ++x) {
        const auto value = coefficients_[y*8+x];
        samples_[offset+y*stride+x] = intra_ ? int16_t(std::clamp(int(value), 0, 255)) : value;
    }
    nextBlock();
}
bool IpuBlockDecoder::step(IpuBitstream& input, std::unordered_map<uint32_t,uint32_t>& io,
                           std::span<const uint8_t> ram) {
    const bool mpeg1 = (control_ & (1u << 23)) != 0;
    const bool alternate = intra_ && !mpeg1 && (control_ & (1u << 21));
    const auto& scan = control_ & (1u << 20) ? alternate_scan : normal_scan;
    if (!pattern_ready_) {
        if (!input.ensure(32, io, ram)) return false;
        const auto code = input.peek(16);
        const auto& entry = code >= 0x2000 ? CBP_7[(code >> 9)-16] : CBP_9[code >> 7];
        if (!entry.len) { error_ = true; return true; }
        pattern_ = entry.cbp; input.advance(entry.len); pattern_ready_ = true;
    }
    while (block_ < 6) {
        if (!(pattern_ & (1u << (5-block_)))) { nextBlock(); continue; }
        if (intra_ && !dc_ready_) {
            if (!input.ensure(32, io, ram)) return false;
            const auto data = input.peek(32); const unsigned prefix = data >> 27;
            const unsigned component = block_ < 4 ? 0 : block_-3;
            const DCtab* entry;
            if (!component) entry = prefix < 31 ? &DCtable.lum0[prefix] : &DCtable.lum1[(data >> 23)-0x1f0];
            else entry = prefix < 31 ? &DCtable.chrom0[prefix] : &DCtable.chrom1[(data >> 22)-0x3e0];
            if (!entry->len || entry->size > 11) { error_ = true; return true; }
            const unsigned count = entry->len + entry->size;
            int difference = 0;
            if (entry->size) {
                difference = int((data >> (32-count)) & ((1u << entry->size)-1));
                if (!(difference & (1u << (entry->size-1)))) difference -= int((1u << entry->size)-1);
            }
            predictors_[component] = int16_t(int(predictors_[component]) + difference);
            coefficients_[0] = int16_t(int(predictors_[component]) * (1 << (3-((control_ >> 16) & 3))));
            input.advance(count); dc_ready_ = true;
        }
        if (!input.ensure(32, io, ram)) return false;
        const auto data = input.peek(32);
        const auto* entry = symbol(data >> 16, alternate, !intra_ && coefficient_ == 0);
        if (!entry || !entry->len) { error_ = true; return true; }
        if (entry->run == 64) { input.advance(entry->len); finishBlock(); continue; }
        unsigned consumed = entry->len, run = entry->run;
        const auto part = [&](unsigned count) {
            const auto value = (data >> (32-consumed-count)) & ((1u << count)-1);
            consumed += count; return value;
        };
        int level;
        if (run == 65) {
            run = part(6);
            if (!mpeg1) level = signedBits(part(12), 12);
            else {
                level = signedBits(part(8), 8);
                if (!(level & 127)) level = int(part(8)) + 2*level;
            }
        } else {
            level = entry->level;
            if (part(1)) level = -level;
        }
        const unsigned target = coefficient_ + run;
        if (target >= 64 || consumed > 32 || level == 0) { error_ = true; return true; }
        const int matrix = input.quant_[target + (intra_ ? 0 : 64)];
        int value;
        if (entry->run == 65) {
            const int sign = level < 0 ? -1 : 0;
            if (intra_) value = (level * int(scale_) * matrix) >> 4;
            else {
                const int product = (2*(level+sign)+1) * int(scale_) * matrix;
                value = mpeg1 ? product/32 : product >> 5;
            }
            if (mpeg1) value = (value + ~(value < 0 ? -1 : 0)) | 1;
        } else {
            const int magnitude = std::abs(level);
            value = intra_ ? (magnitude * int(scale_) * matrix) >> 4 :
                ((2*magnitude+1) * int(scale_) * matrix) >> 5;
            if (intra_ && mpeg1) value = (value-1) | 1;
            if (level < 0) value = -value;
        }
        coefficients_[permute(scan[target])] = int16_t(std::clamp(value, -2048, 2047));
        input.advance(consumed); coefficient_ = target+1;
    }
    return true;
}
}
