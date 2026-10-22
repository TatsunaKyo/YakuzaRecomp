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
    memory.setVu1MscalCallback([&](uint32_t pc, uint32_t, uint32_t) { calledPC = pc; });
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
    std::cout << "VIF commands, split DIRECT payloads, IMAGE continuations and reset pass\n";
}
