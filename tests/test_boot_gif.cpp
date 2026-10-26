// SPDX-License-Identifier: GPL-3.0-or-later
// Original-free GIF PATH3 stream regression; no display or guest program.
#include "runtime/gs/gs_frontend.h"
#include "runtime/gs/ps2_gif_arbiter.h"
#include <array>
#include <cstring>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <vector>

using Bytes = std::vector<uint8_t>;
void check(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
void word(Bytes& out, uint64_t value) {
    const auto* p = reinterpret_cast<const uint8_t*>(&value);
    out.insert(out.end(), p, p + sizeof(value));
}
void ad(Bytes& out, uint8_t reg, uint64_t value) { word(out, value); word(out, reg); }
Bytes setup() {
    Bytes out;
    word(out, 4ull | (1ull << 60)); word(out, 0xe);
    ad(out, 0x50, (0x100ull << 32) | (1ull << 48)); // CT32 destination.
    ad(out, 0x51, 0);
    ad(out, 0x52, 4ull | (1ull << 32));
    ad(out, 0x53, 0);
    return out;
}
Bytes image() {
    Bytes out;
    word(out, 1ull | (1ull << 15) | (2ull << 58)); word(out, 0);
    // Pixel bytes deliberately resemble a valid GIFtag. They remain pixels.
    word(out, 1ull | (1ull << 60)); word(out, 0xe);
    return out;
}
Bytes regPacket(uint8_t reg, uint64_t value) {
    Bytes out; word(out, 1ull | (1ull << 15) | (1ull << 60)); word(out, 0xe);
    ad(out, reg, value); return out;
}
struct Fixture {
    Bytes vram = Bytes(4u * 1024u * 1024u);
    std::unique_ptr<GS> gs = std::make_unique<GS>();
    GifArbiter gif;
    Fixture() {
        gs->init(vram.data(), uint32_t(vram.size()));
        gif.setProcessPacketFn([&](const uint8_t* data, uint32_t size) { gs->processGIFPacket(data, size); });
    }
    void send(const uint8_t* p, size_t n) { gif.submit(GifPathId::Path3, p, uint32_t(n)); gif.drain(); }
    void verify() {
        const std::array<uint32_t, 4> expected{1, 0x10000000u, 0xe, 0};
        for (unsigned x = 0; x < expected.size(); ++x)
            check(gs->ReadVram(0, 0x100, 1, x, 0) == expected[x], "Split PATH3 IMAGE lost or interpreted pixel bytes");
        check(gif.empty(), "Completed GIF stream retained pending bytes");
    }
};
int main() {
    const auto config = setup(), pixels = image();
    {
        Fixture f; f.send(config.data(), config.size());
        f.send(pixels.data(), 16);
        check(!f.gif.empty(), "GIF IMAGE tag lost before DMA data arrived");
        check(f.gs->ReadVram(0, 0x100, 1, 0, 0) == 0, "Incomplete IMAGE produced pixels");
        const auto path1 = regPacket(0x3b, 0x80); // TEXA on another path.
        f.gif.submit(GifPathId::Path1, path1.data(), uint32_t(path1.size())); f.gif.drain();
        check(f.gs->getDebugSnapshot().texa.ta0 == 0x80, "Partial PATH3 consumed another path's registers");
        const auto directHl = regPacket(0x47, 0x1234);
        f.gif.submit(GifPathId::Path2, directHl.data(), uint32_t(directHl.size()), true); f.gif.drain();
        check(f.gs->getDebugSnapshot().ctx[0].test != 0x1234, "DIRECTHL preempted incomplete PATH3 IMAGE");
        f.send(pixels.data() + 16, 16);
        f.verify();
        check(f.gs->getDebugSnapshot().ctx[0].test == 0x1234, "Completed PATH3 left DIRECTHL blocked");
    }
    Bytes combined = config; combined.insert(combined.end(), pixels.begin(), pixels.end());
    {
        Fixture f;
        f.gif.submit(GifPathId::Path3, combined.data(), uint32_t(combined.size()));
        const auto directHl = regPacket(0x47, 0x4321);
        f.gif.submit(GifPathId::Path2, directHl.data(), uint32_t(directHl.size()), true);
        f.gif.drain();
        f.verify(); // Transfer setup must precede its own IMAGE payload.
    }
    for (size_t cut = 1; cut < combined.size(); ++cut) {
        Fixture f; f.send(combined.data(), cut); f.send(combined.data() + cut, combined.size() - cut); f.verify();
    }
    {
        Fixture f;
        for (size_t i = 0; i < combined.size(); ++i) f.send(combined.data() + i, 1);
        f.verify();
    }
    std::cout << "PATH3 header/pixel splits, opaque payload, interleaved paths and DIRECTHL ordering pass\n";
}
