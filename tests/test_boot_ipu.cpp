// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic MPEG start codes through the actual EE MMIO and DMA paths.
#include "runtime/ps2_memory.h"
#include "ps2_runtime.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>

void check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
constexpr uint32_t cmd = 0x10002000, ctrl = 0x10002010, bp = 0x10002020;
void feed(PS2Memory& memory, const uint8_t* bytes) {
    memory.write128(0x10007010, _mm_loadu_si128(reinterpret_cast<const __m128i*>(bytes)));
}
uint32_t bits(PS2Memory& memory, unsigned advance) {
    memory.write32(cmd, 0x40000000 | advance);
    const auto value = memory.read64(cmd);
    check((value >> 63) == 0, "FDEC remained busy with sufficient input");
    return uint32_t(value);
}
void blockTests(PS2Memory& memory) {
    const auto packet = [&](std::string data) {
        data.append((8-data.size()%8)%8, '0');
        data += "00000000000000000000000110110011"; // Sequence start code.
        std::array<uint8_t, 32> stream{};
        check(data.size() <= stream.size()*8, "Synthetic block exceeds input buffer");
        for (unsigned i=0; i<data.size(); ++i)
            if (data[i]=='1') stream[i/8] |= uint8_t(1u << (7-i%8));
        feed(memory, stream.data()); feed(memory, stream.data()+16);
    };
    const auto output = [&](uint32_t address) {
        memory.write32(0x1000e010, 1u << 3); // Clear prior completion.
        memory.write32(0x1000b010, address);
        memory.write32(0x1000b020, 48);
        memory.write32(0x1000b000, 0x100);
    };
    const auto reset = [&] {
        memory.write32(ctrl, 1u << 30);
        memory.write32(0x1000b000, 0);
        memory.write32(0x1000e000, 1);
    };
    const auto done = [&](uint32_t address, unsigned pattern) {
        const auto status = memory.read32(ctrl);
        check(!(status & 0x80000000u), "BDEC remained busy after a complete macroblock");
        check(!(status & 0x4000), "BDEC rejected a valid macroblock");
        check(status & 0x8000, "BDEC failed to report the following start code");
        check(((status >> 8)&63)==pattern, "BDEC coded-block pattern differs");
        check(memory.read32(0x1000b020)==0, "FROM_IPU output count did not reach zero");
        check(memory.read32(0x1000b010)==address+768, "FROM_IPU address did not advance");
        check(!(memory.read32(0x1000b000)&0x100), "FROM_IPU retained STR");
        check(memory.read32(0x1000e010)&8, "FROM_IPU completion was not signaled");
    };
    const auto uniform = [&](uint32_t address, uint16_t expected) {
        for (unsigned i=0; i<384; ++i)
            check(memory.read16(address+2*i)==expected, "BDEC uniform sample differs");
    };
    const std::string flat = "1001010010100101001000100010";
    for (uint32_t destination : {0x30000u, 0x80001800u}) {
        reset(); output(destination); packet(flat);
        memory.write32(cmd, 0x2c010000);
        done(destination, 63);
        uniform(destination & 0x80000000u ? 0x70001800u : destination, 128);
    }
    reset(); packet(flat); memory.write32(cmd, 0x2c010000);
    check(memory.read32(ctrl)&0x80000000u, "BDEC ignored output FIFO backpressure");
    check(((memory.read32(ctrl)>>4)&15)==8, "BDEC did not fill its eight-qword output FIFO");
    output(0x30000); done(0x30000, 63); uniform(0x30000, 128);

    // Stop after the first DC code, resume when the next input qword arrives.
    reset(); output(0x30000); memory.write32(cmd, 95);
    std::string split(95, '0'); split += flat;
    split.append((8-split.size()%8)%8, '0');
    split += "00000000000000000000000110110011";
    std::array<uint8_t,32> chunks{};
    for (unsigned i=0; i<split.size(); ++i)
        if (split[i]=='1') chunks[i/8] |= uint8_t(1u << (7-i%8));
    memory.write32(cmd, 0x2c010000); feed(memory, chunks.data());
    check(memory.read32(ctrl)&0x80000000u, "BDEC did not wait for a split coefficient stream");
    check(memory.read32(0x1000b020)==48, "BDEC fabricated output before the complete block");
    feed(memory, chunks.data()+16); done(0x30000,63); uniform(0x30000,128);

    // Actual game flags: alternate intra VLC, nonlinear scale, DC precision 10.
    reset(); memory.write32(ctrl, 0x01620000); output(0x30000);
    packet("1000110100011010001101000110000110000110");
    memory.write32(cmd, 0x2c010000); done(0x30000, 63); uniform(0x30000, 128);

    reset(); output(0x30000); packet("000000001");
    memory.write32(cmd, 0x20080000); done(0x30000, 0); uniform(0x30000, 0);
    const auto matrix = [&](bool intra) {
        memory.write32(cmd, intra ? 0x50000000 : 0x58000000);
        std::array<uint8_t,16> values; values.fill(16);
        for (unsigned i=0; i<4; ++i) feed(memory, values.data());
    };
    for (bool negative : {false, true}) for (bool field : {false, true}) {
        reset(); matrix(false); output(0x30000);
        packet(negative ? "10101110" : "10101010");
        memory.write32(cmd, 0x20080000 | (field ? 1u << 25 : 0));
        done(0x30000, 32);
        for (unsigned i=0; i<384; ++i) {
            const unsigned row=i/16, column=i%16;
            const bool firstBlock = i<256 && column<8 && (field ? row%2==0 : row<8);
            const auto expected = uint16_t(firstBlock ? (negative ? -3 : 3) : 0);
            check(memory.read16(0x30000+2*i)==expected, "BDEC residual or field placement differs");
        }
    }
    reset(); matrix(true); output(0x30000);
    packet("1001101010010100101001000100010");
    memory.write32(cmd, 0x2c080000); done(0x30000, 63);
    const std::array<uint16_t,8> ac{131,130,130,129,127,126,126,125};
    for (unsigned i=0; i<384; ++i) {
        const unsigned row=i/16, column=i%16;
        const auto expected = i<256 && row<8 && column<8 ? ac[column] : 128;
        check(memory.read16(0x30000+2*i)==expected, "BDEC AC/IDCT golden sample differs");
    }
    reset(); output(0x02000000); packet(flat);
    bool rejected=false;
    try { memory.write32(cmd, 0x2c010000); }
    catch (const std::runtime_error&) { rejected=true; }
    check(rejected, "FROM_IPU DMA wrote beyond EE RAM");
}
int main() {
    PS2Memory memory;
    check(memory.initialize(), "Memory initialization failed");
    // Sequence header, then arbitrary bits. These bytes are synthetic.
    const std::array<uint8_t, 32> bytes{0,0,1,0xb3,0x20,1,0x80,0x13,
        0x12,0x34,0x56,0x78,0x9a,0xbc,0xde,0xf0,
        0x10,0x32,0x54,0x76,0x98,0xba,0xdc,0xfe};
    memory.write32(cmd, 0); // BCLR before supplying input.
    feed(memory, bytes.data());
    feed(memory, bytes.data() + 16);
    check(bits(memory, 0) == 0x000001b3, "IPU returned its command instead of MPEG input bits");
    check(bits(memory, 0) == 0x000001b3, "FDEC peek consumed bits");
    check(bits(memory, 32) == 0x20018013, "FDEC did not advance by the declared bit count");
    check(bits(memory, 63) == 0x4d5e6f78, "Unaligned FDEC bit order is incorrect");
    check(bits(memory, 32) == 0x08192a3b, "FDEC lost bits across a qword boundary");

    memory.write32(ctrl, 1u << 30);
    memory.write32(cmd, 0x40000000);
    check((memory.read64(cmd) >> 63) == 1, "Empty IPU command did not retain BUSY");
    check(memory.read32(ctrl) & (1u << 31), "IPU CTRL did not report pending input");
    feed(memory, bytes.data());
    check(memory.read64(cmd) == 0x000001b3, "FIFO delivery did not finish a pending FDEC");
    check(!(memory.read32(ctrl) & (1u << 31)), "Completed FDEC retained BUSY");

    // Normal TO_IPU DMA must retain backpressure until the FIFO is consumed.
    memory.write32(ctrl, 1u << 30);
    for (unsigned i = 0; i < 12 * 16; ++i) memory.write8(0x10000 + i, uint8_t(i));
    memory.write32(0x1000e000, 1);
    memory.write32(0x1000b410, 0x10000);
    memory.write32(0x1000b420, 12);
    memory.write32(0x1000b400, 0x101);
    check(memory.read32(0x1000b420) != 0, "TO_IPU DMA ignored FIFO backpressure");
    check(bits(memory, 0) == 0x00010203, "TO_IPU DMA did not supply the original bytes");
    for (unsigned word = 1; word < 48; ++word) {
        const unsigned byte = word * 4;
        const uint32_t expected = (byte << 24) | ((byte + 1) << 16) | ((byte + 2) << 8) | (byte + 3);
        check(bits(memory, 32) == expected, "TO_IPU DMA lost or duplicated a qword");
    }
    check(memory.read32(0x1000b420) == 0, "TO_IPU QWC did not reach zero");
    check(memory.read32(0x1000b410) == 0x100c0, "TO_IPU MADR did not advance");
    check(!(memory.read32(0x1000b400) & 0x100), "Completed TO_IPU DMA retained STR");
    check(memory.read32(0x1000e010) & (1u << 4), "TO_IPU DMA completion was not signaled");
    check((memory.read32(bp) & 127) == 96, "IPU bit position differs from consumed input");

    // REF followed by END: tag bytes must not enter the MPEG bitstream.
    memory.write32(ctrl, 1u << 30);
    memory.write32(0x20000, (3u << 28) | 1);
    memory.write32(0x20004, 0x21000);
    memory.write32(0x20010, (7u << 28) | 1);
    for (unsigned i = 0; i < 16; ++i) {
        memory.write8(0x21000 + i, bytes[i]);
        memory.write8(0x20020 + i, i == 2 ? 1 : 0);
    }
    memory.write32(0x1000b420, 0);
    memory.write32(0x1000b430, 0x20000);
    memory.write32(0x1000b400, 0x105);
    check(bits(memory, 0) == 0x000001b3, "REF chain input differs from source");
    bits(memory, 63); bits(memory, 63);
    check(bits(memory, 2) == 0x00000100, "DMA tag bytes leaked into the END payload");
    check(memory.read32(0x1000b410) == 0x20030, "END payload address was not retained");
    check(memory.read32(0x1000b430) == 0x20030, "DMA chain TADR did not advance");

    for (const unsigned operation : {5u, 6u}) {
        memory.write32(ctrl, 1u << 30);
        memory.write32(cmd, operation << 28);
        const unsigned count = operation == 5 ? 4 : 2;
        for (unsigned i = 0; i < count; ++i) {
            check(memory.read32(ctrl) & (1u << 31), "IPU table command completed before all input arrived");
            feed(memory, bytes.data());
        }
        check(!(memory.read32(ctrl) & (1u << 31)), "IPU table input did not complete");
        feed(memory, bytes.data());
        check(bits(memory, 0) == 0x000001b3, "IPU table load consumed subsequent stream bytes");
    }
    const std::array<std::pair<std::string_view, uint32_t>, 6> mba_vectors{{
        {"1",0x10001}, {"011",0x30002}, {"0000111",0x70008},
        {"0000010111",0xa0010}, {"00000011000",0xb0021}, {"00000001000",0xb0023}}};
    const auto mba = [&](std::string_view code, uint32_t expected, bool mpeg1, unsigned prefix = 0,
                         uint32_t operation = 0x30000000, uint32_t control = 0) {
        memory.write32(ctrl, 1u << 30);
        memory.write32(ctrl, control | (mpeg1 ? 1u << 23 : 0));
        memory.write32(cmd, prefix);
        std::array<uint8_t, 32> stream{};
        const std::string packet = std::string(prefix, '0') + std::string(code) + "10101100";
        for (unsigned i = 0; i < packet.size(); ++i)
            if (packet[i] == '1') stream[i/8] |= uint8_t(1u << (7-i%8));
        memory.write32(cmd, operation);
        check(memory.read32(ctrl) & (1u << 31), "Empty VDEC did not wait for input");
        feed(memory, stream.data());
        if (prefix) check(memory.read32(ctrl) & (1u << 31), "Cross-qword VDEC finished without enough input");
        feed(memory, stream.data()+16);
        check(memory.read64(cmd) == expected, "Macroblock address VLC result differs");
        check(bool(memory.read32(ctrl) & 0x4000) == (expected == 0), "VDEC error status differs");
        const unsigned consumed = expected ? unsigned(code.size()) : 0;
        check((memory.read32(bp) & 127) == (prefix + consumed) % 128, "VDEC consumed the wrong number of bits");
        if (expected) check(memory.read32(cmd+0x30) >> 28 == 10, "VDEC TOP lost following stream bits");
    };
    for (const auto& [code, expected] : mba_vectors) mba(code, expected, false);
    mba("00000001111", 0xb0022, true); // MPEG-1 stuffing.
    mba("00000001111", 0, false); // Illegal MPEG-2 stuffing.
    mba("00000000000", 0, false);
    mba("1", 0x10001, false, 127);
    mba("1", 1, false, 0, 0x34000000, 1u << 24); // I picture: intra.
    mba("01", 17, false, 0, 0x34000000, 1u << 24); // Intra plus quantizer.
    mba("1", 0x8a, false, 0, 0x34000000, 2u << 24); // P: forward plus pattern.
    mba("001", 0x88, false, 0, 0x34000000, 2u << 24); // P: forward.
    mba("10", 0x2008c, false, 0, 0x34000000, 3u << 24); // B: both directions.
    mba("000001", 0x60091, false, 0, 0x34000000, 3u << 24);
    mba("1", 0x10001, false, 0, 0x34000000, 4u << 24); // D picture.
    mba("00", 0, false, 0, 0x34000000, 1u << 24);
    mba("1", 0x10000, false, 0, 0x38000000); // Zero motion code.
    mba("010", 0x20001, false, 0, 0x38000000);
    mba("011", 0xffffffff, false, 0, 0x38000000);
    mba("0010", 0x30002, false, 0, 0x38000000);
    mba("00000000000", 0, false, 0, 0x38000000);
    mba("0", 0x10000, false, 0, 0x3c000000); // Dual-prime differential vectors.
    mba("10", 0x20001, false, 0, 0x3c000000);
    mba("11", 0xffffffff, false, 0, 0x3c000000);
    memory.write32(ctrl, 1u << 30);
    bool rejected = false;
    try {
        memory.write32(0x1000b410, 0x02000000);
        memory.write32(0x1000b420, 1);
        memory.write32(0x1000b400, 0x101);
    } catch (const std::runtime_error&) { rejected = true; }
    check(rejected, "IPU DMA read beyond EE RAM was accepted");
    memory.write32(0x1000b400, 0);
    memory.write32(ctrl, 1u << 30);
    rejected = false;
    try { memory.write32(cmd, 0x10000000); }
    catch (const std::runtime_error&) { rejected = true; }
    check(rejected, "Unimplemented IPU picture decode falsely completed");
    PS2Runtime runtime;
    check(runtime.memory().initialize(), "Runtime memory initialization failed");
    auto* ram = runtime.memory().getRDRAM();
    R5900Context context{};
    context.pc = 0x100008;
    for (unsigned width : {32u, 64u, 128u}) {
        rejected = false;
        try {
            if (width == 32) runtime.Store32(ram, &context, cmd, 0x10000000);
            else if (width == 64) runtime.Store64(ram, &context, cmd, 0x10000000);
            else runtime.Store128(ram, &context, cmd, _mm_set_epi32(0, 0, 0, 0x10000000));
        } catch (const std::runtime_error&) { rejected = true; }
        check(rejected, "Runtime memory helper swallowed an unsupported IPU command");
    }
    // An ordinary guest address error keeps the existing guest-fault behavior.
    check(runtime.Load32(ram, &context, 0x10001) == 0, "Guest address faults changed behavior");
    blockTests(memory);
    std::cout << "IPU bits, VLC, block/IDCT golden pixels, input/output DMA, waits and explicit limits pass\n";
}
