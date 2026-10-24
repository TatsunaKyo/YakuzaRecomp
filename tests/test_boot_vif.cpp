// SPDX-License-Identifier: GPL-3.0-or-later
// Synthetic VIF/GIF stream regression. No original assets or display needed.
#include "runtime/ps2_memory.h"
#include <algorithm>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <utility>
#include <vector>

using Bytes = std::vector<uint8_t>;
void check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
template<class T> void append(Bytes& bytes, T value) {
    const auto* p = reinterpret_cast<const uint8_t*>(&value);
    bytes.insert(bytes.end(), p, p + sizeof(value));
}
void imageTag(Bytes& bytes, unsigned qwc) {
    append(bytes, uint64_t(qwc) | (1ull << 15) | (2ull << 58));
    append(bytes, uint64_t(0));
}
void direct(Bytes& bytes, const Bytes& payload, bool hl = false) {
    check(payload.size() % 16 == 0, "Invalid synthetic DIRECT payload");
    append(bytes, uint32_t((hl ? 0x51000000u : 0x50000000u) | (payload.size() / 16)));
    bytes.insert(bytes.end(), payload.begin(), payload.end());
}

int main() {
    PS2Memory memory;
    check(memory.initialize(), "Memory initialization failed");
    Bytes received;
    uint32_t calledPC = 0;
    unsigned callCount = 0;
    memory.setVu1MscalCallback([&](uint32_t pc, uint32_t, uint32_t) { calledPC = pc; ++callCount; });
    memory.setGifPacketCallback([&](const uint8_t* data, uint32_t size) {
        // IMAGE tags may arrive before their data. Inspect only bytes actually
        // delivered to GIF; a truncated tag cannot provide any pixels yet.
        for (unsigned offset = 0; offset + 16 <= size;) {
            uint64_t tag = 0;
            std::memcpy(&tag, data + offset, 8);
            offset += 16;
            check(((tag >> 58) & 3) == 2, "Unexpected GIF tag in image upload");
            const unsigned count = std::min(unsigned(tag & 0x7fff) * 16, size - offset);
            received.insert(received.end(), data + offset, data + offset + count);
            offset += count;
        }
    });
    Bytes pixels;
    // Deliberately resemble VIF commands. Pixel content must never decide
    // whether a byte is a command; only DIRECT's declared length can do that.
    for (unsigned i = 0; i < 16; ++i) append(pixels, uint32_t(0x51000004u + i));
    Bytes tag; imageTag(tag, 4);
    Bytes first; direct(first, tag);
    memory.processVIF1Data(first.data(), uint32_t(first.size()));
    Bytes next; append(next, uint32_t(0)); direct(next, pixels, true);
    append(next, uint32_t(0x14000023)); // MSCAL after the image.
    memory.processVIF1Data(next.data(), uint32_t(next.size()));
    check(received == pixels, "VIF command bytes leaked into the image payload");
    check(calledPC == 0x118, "Command after image was not parsed");

    received.clear();
    Bytes combined = tag;
    combined.insert(combined.end(), pixels.begin(), pixels.end());
    Bytes fragmented; direct(fragmented, combined);
    // One DIRECT spans several DMA/FIFO deliveries, including a half-qword.
    for (const auto& part : std::vector<std::pair<unsigned, unsigned>>{{0, 12}, {12, 24}, {36, 48}})
        memory.processVIF1Data(fragmented.data() + part.first, part.second);
    check(received == pixels, "Split DIRECT lost or misclassified image bytes");

    received.clear();
    memory.processVIF1Data(first.data(), uint32_t(first.size()));
    Bytes halves;
    direct(halves, Bytes(pixels.begin(), pixels.begin() + 32), true);
    append(halves, uint32_t(0));
    direct(halves, Bytes(pixels.begin() + 32, pixels.end()));
    memory.processVIF1Data(halves.data(), uint32_t(halves.size()));
    check(received == pixels, "IMAGE continuation across DIRECT commands failed");

    received.clear();
    memory.processVIF1Data(first.data(), uint32_t(first.size()));
    memory.processVIF1Data(fragmented.data(), 12);
    memory.write32(0x10003c10, 1); // FBRST discards both pending streams.
    memory.processVIF1Data(fragmented.data(), uint32_t(fragmented.size()));
    check(received == pixels, "VIF reset retained an incomplete transfer");

    Bytes micro;
    for (unsigned i = 0; i < 16; ++i) append(micro, uint32_t(0x14000100u + i));
    Bytes upload;
    append(upload, uint32_t(0x4a080020)); // Eight VU instruction pairs, destination 0x100.
    upload.insert(upload.end(), micro.begin(), micro.end());
    append(upload, uint32_t(0x14000023));
    memory.write32(0x10003c10, 1);
    std::fill_n(memory.getVU1Code() + 0x100, micro.size(), uint8_t{0});
    memory.processVIF1Data(upload.data(), 16); // One FIFO qword includes a partial program.
    memory.processVIF1Data(upload.data() + 16, uint32_t(upload.size() - 16));
    check(std::equal(micro.begin(), micro.end(), memory.getVU1Code() + 0x100),
          "Split MPG lost original instruction bytes");

    unsigned boundaries = 0;
    const auto everyBoundary = [&](const Bytes& commands, auto prepare, auto verify) {
        for (unsigned cut = 1; cut < commands.size(); ++cut) {
            memory.write32(0x10003c10, 1);
            calledPC = callCount = 0;
            prepare();
            memory.processVIF1Data(commands.data(), cut);
            memory.processVIF1Data(commands.data() + cut, uint32_t(commands.size() - cut));
            verify();
            check(calledPC == 0x118 && callCount == 1, "Payload or partial header became a VIF command");
            ++boundaries;
        }
    };
    everyBoundary(upload, [&] { std::fill_n(memory.getVU1Code() + 0x100, micro.size(), uint8_t{0}); }, [&] {
        check(std::equal(micro.begin(), micro.end(), memory.getVU1Code() + 0x100), "Fragmented MPG changed its program");
    });
    memory.write32(0x10003c10, 1);
    calledPC = callCount = 0;
    std::fill_n(memory.getVU1Code() + 0x100, micro.size(), uint8_t{0});
    for (const auto& byte : upload) memory.processVIF1Data(&byte, 1);
    check(std::equal(micro.begin(), micro.end(), memory.getVU1Code() + 0x100), "Repeated MPG continuation lost bytes");
    check(calledPC == 0x118 && callCount == 1, "Repeated continuation executed payload as commands");

    Bytes vertices;
    for (unsigned i = 0; i < 8; ++i) append(vertices, uint32_t(0x14000200u + i));
    Bytes unpack;
    append(unpack, uint32_t(0x6c020012)); // Two V4_32 vectors, destination qword 0x12.
    unpack.insert(unpack.end(), vertices.begin(), vertices.end());
    append(unpack, uint32_t(0x14000023));
    everyBoundary(unpack, [&] { std::fill_n(memory.getVU1Data() + 0x120, vertices.size(), uint8_t{0}); }, [&] {
        check(std::equal(vertices.begin(), vertices.end(), memory.getVU1Data() + 0x120), "Fragmented UNPACK changed vertex bytes");
    });

    Bytes registers;
    append(registers, uint32_t(0x20000000)); append(registers, uint32_t(0x31415926));
    append(registers, uint32_t(0x30000000));
    for (unsigned i = 0; i < 4; ++i) append(registers, uint32_t(0x14000300u + i));
    append(registers, uint32_t(0x31000000));
    for (unsigned i = 0; i < 4; ++i) append(registers, uint32_t(0x14000400u + i));
    append(registers, uint32_t(0x14000023));
    everyBoundary(registers, [] {}, [&] {
        check(memory.vif1_regs.mask == 0x31415926, "Fragmented STMASK lost its value");
        for (unsigned i = 0; i < 4; ++i) {
            check(memory.vif1_regs.row[i] == 0x14000300u + i, "Fragmented STROW changed a lane");
            check(memory.vif1_regs.col[i] == 0x14000400u + i, "Fragmented STCOL changed a lane");
        }
    });

    // NUM=0 means 256 instructions/vectors; include the largest legal payloads.
    Bytes maximumMicro(2048), maximumVertices(4096);
    for (unsigned i = 0; i < maximumMicro.size(); ++i) maximumMicro[i] = uint8_t(i * 17u + 3u);
    for (unsigned i = 0; i < maximumVertices.size(); ++i) maximumVertices[i] = uint8_t(i * 19u + 5u);
    Bytes maximumUpload; append(maximumUpload, uint32_t(0x4a000100));
    maximumUpload.insert(maximumUpload.end(), maximumMicro.begin(), maximumMicro.end());
    append(maximumUpload, uint32_t(0x14000023));
    everyBoundary(maximumUpload, [&] { std::fill_n(memory.getVU1Code() + 0x800, maximumMicro.size(), uint8_t{0}); }, [&] {
        check(std::equal(maximumMicro.begin(), maximumMicro.end(), memory.getVU1Code() + 0x800), "NUM=0 MPG fragmentation failed");
    });
    Bytes maximumUnpack; append(maximumUnpack, uint32_t(0x6c000000));
    maximumUnpack.insert(maximumUnpack.end(), maximumVertices.begin(), maximumVertices.end());
    append(maximumUnpack, uint32_t(0x14000023));
    everyBoundary(maximumUnpack, [&] { std::fill_n(memory.getVU1Data(), maximumVertices.size(), uint8_t{0}); }, [&] {
        check(std::equal(maximumVertices.begin(), maximumVertices.end(), memory.getVU1Data()), "NUM=0 UNPACK fragmentation failed");
    });

    memory.write32(0x10003c10, 1);
    Bytes interrupted = upload;
    interrupted[3] |= 0x80; // Command IRQ, acknowledged while its payload is incomplete.
    memory.processVIF1Data(interrupted.data(), 16);
    check(memory.vif1_regs.stat & (1u << 11), "Command IRQ was not observed");
    memory.write32(0x10003c10, 8); // STC acknowledges without resetting the transfer.
    memory.processVIF1Data(interrupted.data() + 16, uint32_t(interrupted.size() - 16));
    check(!(memory.vif1_regs.stat & (1u << 11)), "Continuation reasserted an acknowledged command IRQ");

    memory.processVIF1Data(upload.data(), 16);
    memory.write32(0x10003c10, 1);
    calledPC = callCount = 0;
    const uint32_t afterReset = 0x14000023;
    memory.processVIF1Data(reinterpret_cast<const uint8_t*>(&afterReset), sizeof(afterReset));
    check(calledPC == 0x118 && callCount == 1, "VIF reset retained an incomplete MPG payload");
    memory.processVIF1Data(registers.data(), 2);
    memory.write32(0x10003c10, 1);
    calledPC = callCount = 0;
    memory.processVIF1Data(reinterpret_cast<const uint8_t*>(&afterReset), sizeof(afterReset));
    check(calledPC == 0x118 && callCount == 1, "VIF reset retained a partial command word");
    std::cout << "VIF DIRECT/IMAGE, " << boundaries << " command fragmentation boundaries, IRQ acknowledgement and reset pass\n";
}
