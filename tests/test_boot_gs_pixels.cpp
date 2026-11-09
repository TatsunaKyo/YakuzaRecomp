// SPDX-License-Identifier: GPL-3.0-or-later
#include "runtime/gs/gs_cpu_backend.h"
#include "runtime/gs/ps2_gs_memory.h"

#include <algorithm>
#include <iostream>
#include <vector>

namespace {
constexpr uint32_t kSourceRgb = 0xfa3ed2u;
constexpr uint32_t kDestination = 0x9f18c835u;
constexpr uint32_t kAlwaysDepth = 1u << 17u;
constexpr uint32_t kDepthBase = 32u * 32u;
constexpr uint32_t kX = 3, kY = 4;

uint32_t referenceBlend(uint32_t source, uint32_t destination, uint8_t mode, int fix) {
    const auto component = [](uint32_t color, unsigned shift) {
        return static_cast<int>((color >> shift) & 0xffu);
    };
    const unsigned c = (mode >> 4u) & 3u;
    const int factor = c == 0 ? component(source, 24) : c == 1 ? component(destination, 24) : fix;
    uint32_t result = source & 0xff000000u;
    for (unsigned shift : {0u, 8u, 16u}) {
        const int channels[] = {component(source, shift), component(destination, shift), 0, 0};
        const int a = channels[mode & 3u];
        const int b = channels[(mode >> 2u) & 3u];
        const int d = channels[mode >> 6u];
        result |= static_cast<uint32_t>(std::clamp(d + ((a - b) * factor >> 7), 0, 255)) << shift;
    }
    return result;
}
}

int main() {
    std::vector<uint8_t> vram(GSMem::MEMORY_SIZE);
    GSCpuBackend backend;
    backend.Initialize(vram.data(), static_cast<uint32_t>(vram.size()));
    GSPrimitiveBatch batch{};
    batch.vertexCount = 1;
    auto &state = batch.state;
    state.context.frame = {0, 1, GS_PSM_CT32, 0};
    state.context.zbuf = {32, GS_PSM_Z32, false};
    state.context.scissor = {0, 63, 0, 31};
    state.context.test = kAlwaysDepth;
    state.prim.abe = true;
    auto &vertex = batch.vertices[0];
    vertex.x = kX;
    vertex.y = kY;
    vertex.z = 12;
    vertex.r = static_cast<uint8_t>(kSourceRgb);
    vertex.g = static_cast<uint8_t>(kSourceRgb >> 8u);
    vertex.b = static_cast<uint8_t>(kSourceRgb >> 16u);

    const auto draw = [&](uint32_t expectedColor, uint32_t expectedDepth) {
        backend.WriteVram(GS_PSM_CT32, 0, 1, kX, kY, kDestination);
        backend.WriteVram(GS_PSM_Z32, kDepthBase, 1, kX, kY, 12);
        backend.Submit(batch);
        return backend.ReadVram(GS_PSM_CT32, 0, 1, kX, kY) == expectedColor &&
               backend.ReadVram(GS_PSM_Z32, kDepthBase, 1, kX, kY) == expectedDepth;
    };

    for (unsigned mode = 0; mode <= 0xffu; ++mode) {
        for (unsigned alpha : {0u, 0x7fu, 0x80u, 0xffu}) {
            for (unsigned fix : {0u, 0x80u, 0xffu}) {
                state.context.alpha = (static_cast<uint64_t>(fix) << 32u) | mode;
                vertex.a = static_cast<uint8_t>(alpha);
                const uint32_t source = (alpha << 24u) | kSourceRgb;
                if (!draw(referenceBlend(source, kDestination, static_cast<uint8_t>(mode), fix), 12)) {
                    std::cerr << "Unexpected blend result for mode " << mode << ", alpha " << alpha
                              << ", FIX " << fix << '\n';
                    return 1;
                }
            }
        }
    }

    vertex.a = 0x40;
    vertex.z = 13;
    state.context.alpha = 0x44;
    state.pabe = true;
    if (!draw(0x40fa3ed2u, 13)) return 2;

    state.pabe = false;
    state.context.alpha = 0x2a;
    state.context.frame.psm = GS_PSM_CT24;
    state.context.frame.fbmsk = 0xff00ff00u;
    if (!draw(0x9ffac8d2u, 13)) return 3;
    state.context.frame.fbmsk = 0xff000000u;
    if (!draw(0x9ffa3ed2u, 13)) return 4;

    state.context.frame.psm = GS_PSM_CT32;
    state.context.frame.fbmsk = 0;
    state.context.test = kAlwaysDepth | 1u | (3u << 12u); // Failed alpha, RGB_ONLY.
    if (!draw(0x9ffa3ed2u, 12)) return 5;
    state.context.test = kAlwaysDepth | (1u << 14u); // Destination alpha MSB must be clear.
    if (!draw(kDestination, 12)) return 6;
    state.context.test = 3u << 17u; // Strict greater-than depth test.
    vertex.z = 12;
    if (!draw(kDestination, 12)) return 7;

    std::fill(vram.begin(), vram.end(), 0);
    backend.WriteVram(GS_PSM_CT32, kDepthBase, 1, 0, 0, 0x80ff00ffu);
    GSPresentationRequest request{};
    request.dispfb1 = request.dispfb2 = 1u << 9u; // Page zero, 64-pixel stride.
    request.display1 = request.display2 = (63ull << 32u) | (63ull << 44u);
    request.contextFrames[0] = {32, 1, GS_PSM_CT32, 0};
    for (uint64_t mode : {1u, 2u, 3u}) {
        request.pmode = mode;
        const auto frame = backend.Present(request);
        if (!frame || frame.sourceFbp != 0 || frame.width != 64 || frame.height != 64 ||
            frame.pixels[0] != 0 || frame.pixels[1] != 0 || frame.pixels[2] != 0) {
            std::cerr << "Black scanout selected an off-screen buffer for PMODE " << mode << '\n';
            return 8;
        }
    }
    request.pmode = 1;
    request.hasPreferredSource = true;
    request.preferredSource = {kDepthBase, 1, GS_PSM_CT32, 0};
    const auto preferred = backend.Present(request);
    if (!preferred || !preferred.usedPreferred || preferred.pixels[0] != 255 || preferred.pixels[2] != 255)
        return 9;
    return 0;
}
