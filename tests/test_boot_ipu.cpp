// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic MPEG start codes through the actual EE MMIO and DMA paths.
#include "runtime/ps2_memory.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>

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
    try { memory.write32(cmd, 0x20000000); }
    catch (const std::runtime_error&) { rejected = true; }
    check(rejected, "Unimplemented IPU picture decode falsely completed");
    std::cout << "IPU bits, input waits, reset, normal/chain DMA, tables, bounds and explicit decode limits pass\n";
}
