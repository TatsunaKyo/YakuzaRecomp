"""Retain incomplete PATH3 GIF tags and payloads across DMA submissions.

The existing arbiter queue owns incomplete packets. No runtime header or class
layout changes, original game patches or forced DMA completion are involved.
"""
import hashlib
from prepare_game import require

GIF_ARBITER_SHA256 = "53374b9718550cd366226096bc2b9b4eea1e858eff4b05a73c3ff08a677edd24"

HELPERS = r'''
namespace
{
uint32_t path3TagBytes(const std::vector<uint8_t> &bytes)
{
    if (bytes.size() < 16u)
        return 16u;
    uint64_t tag = 0u;
    std::memcpy(&tag, bytes.data(), sizeof(tag));
    const uint32_t loops = static_cast<uint32_t>(tag & 0x7fffu);
    uint32_t registers = static_cast<uint32_t>((tag >> 60u) & 15u);
    if (registers == 0u)
        registers = 16u;
    const uint32_t format = static_cast<uint32_t>((tag >> 58u) & 3u);
    uint32_t payload = loops * 16u;
    if (format == 0u)
        payload *= registers;
    else if (format == 1u)
        payload = ((loops * registers + 1u) / 2u) * 16u;
    // The tag fields bound a packet to at most 32767 * 16 qwords.
    return 16u + payload;
}

bool incompletePath3(const GifArbiterPacket &packet)
{
    return packet.pathId == GifPathId::Path3 &&
           (packet.data.size() < 16u || packet.data.size() < path3TagBytes(packet.data));
}
}

'''

SUBMIT = r'''void GifArbiter::submit(GifPathId pathId, const uint8_t *data, uint32_t sizeBytes, bool path2DirectHl)
{
    if (!data || sizeBytes == 0u || !m_processFn)
        return;
    if (pathId != GifPathId::Path3)
    {
        if (sizeBytes < 16u)
            return;
        GifArbiterPacket packet;
        packet.pathId = pathId;
        packet.path2DirectHl = pathId == GifPathId::Path2 && path2DirectHl;
        packet.data.assign(data, data + sizeBytes);
        m_queue.push_back(std::move(packet));
        return;
    }

    // A DMA boundary is not a GIFtag boundary. In particular, an IMAGE tag
    // can arrive in one DMA and its opaque pixels in the next DMA.
    auto found = std::find_if(m_queue.begin(), m_queue.end(), incompletePath3);
    size_t index = static_cast<size_t>(found - m_queue.begin());
    uint32_t offset = 0u;
    while (offset < sizeBytes)
    {
        if (index == m_queue.size())
        {
            GifArbiterPacket packet;
            packet.pathId = GifPathId::Path3;
            m_queue.push_back(std::move(packet));
        }
        auto &packet = m_queue[index];
        const uint32_t needed = path3TagBytes(packet.data);
        const uint32_t take = std::min<uint32_t>(needed - static_cast<uint32_t>(packet.data.size()), sizeBytes - offset);
        packet.data.insert(packet.data.end(), data + offset, data + offset + take);
        offset += take;
        if (packet.data.size() >= 16u)
            packet.path3Image = isImagePacket(packet.data.data(), static_cast<uint32_t>(packet.data.size()));
        if (!incompletePath3(packet))
            index = m_queue.size();
    }
}

'''

DRAIN = r'''void GifArbiter::drain()
{
    if (!m_processFn)
        return;
    // Preserve FIFO order within each path. A global IMAGE/DIRECTHL sort
    // could move a completed IMAGE ahead of its own transfer setup tag.
    std::array<std::vector<GifArbiterPacket>, 3> paths;
    for (auto &packet : m_queue)
    {
        const size_t path = packet.pathId == GifPathId::Path1 ? 0u :
                            packet.pathId == GifPathId::Path2 ? 1u : 2u;
        paths[path].push_back(std::move(packet));
    }
    m_queue.clear();
    std::array<size_t, 3> next{};
    for (;;)
    {
        size_t selected = 3u;
        const bool hasPath3 = next[2] < paths[2].size();
        if (next[0] < paths[0].size())
            selected = 0u;
        else if (next[1] < paths[1].size())
        {
            const bool imageBlocksHl = hasPath3 && paths[2][next[2]].path3Image &&
                                       paths[1][next[1]].path2DirectHl;
            if (!imageBlocksHl)
                selected = 1u;
            else if (!incompletePath3(paths[2][next[2]]))
                selected = 2u;
        }
        else if (hasPath3 && !incompletePath3(paths[2][next[2]]))
            selected = 2u;
        if (selected == 3u)
            break;
        const auto &packet = paths[selected][next[selected]++];
        if (!packet.data.empty())
            m_processFn(packet.data.data(), static_cast<uint32_t>(packet.data.size()));
    }
    for (size_t path = 0u; path < paths.size(); ++path)
        for (size_t index = next[path]; index < paths[path].size(); ++index)
            m_queue.push_back(std::move(paths[path][index]));
}

'''


def adapt_path3_gif(data):
    raw = data.replace(b"\r\n", b"\n")
    require(hashlib.sha256(raw).hexdigest() == GIF_ARBITER_SHA256,
            "Unsupported GIF arbiter source; reassess")
    text = raw.decode()
    text = text.replace("#include <cstring>", "#include <cstring>\n#include <array>")
    start = text.index("GifArbiter::GifArbiter(")
    text = text[:start] + HELPERS + text[start:]
    start = text.index("void GifArbiter::submit(")
    end = text.index("void GifArbiter::drain()", start)
    text = text[:start] + SUBMIT + text[end:]
    start = text.index("void GifArbiter::drain()")
    end = text.index("uint8_t GifArbiter::pathPriority", start)
    return (text[:start] + DRAIN + text[end:]).encode()
