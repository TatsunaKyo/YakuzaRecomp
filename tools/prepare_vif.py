"""Adapt the hash-checked runtime's VIF1 DIRECT / GIF IMAGE boundaries."""
from prepare_game import require


def adapt_vif(vif, memory, header):
    anchor = "    uint32_t m_vif1PendingPath2ImageQwc = 0u;\n"
    require(header.count(anchor) == 1, "VIF state layout no longer matches")
    header = header.replace(anchor, anchor + """    uint32_t m_vif1DirectBytesRemaining = 0u;
    std::vector<uint8_t> m_vif1DirectBuffer;
""")
    for indent in ("    ", "                "):
        reset = indent + "m_vif1PendingPath2ImageQwc = 0u;\n"
        require(memory.count("\n" + reset) == 1, "VIF reset site no longer matches")
        memory = memory.replace("\n" + reset, "\n" + reset + indent +
            "m_vif1DirectBytesRemaining = 0u;\n" + indent + "m_vif1DirectBuffer.clear();\n")

    start = vif.index("void PS2Memory::processVIF1Data(const uint8_t *data, uint32_t sizeBytes)")
    loop = vif.index("    while (pos + 4 <= sizeBytes)", start)
    command = vif.index("        uint32_t cmd;", loop)
    vif = vif[:loop] + """    // DIRECT owns only its declared payload. A pending GIF IMAGE never
    // turns subsequent VIF codes into pixels. Buffer a DIRECT split across
    // DMA/FIFO deliveries so neither partial qwords nor GIF tags are lost.
    while (pos < sizeBytes)
    {
        if (m_vif1DirectBytesRemaining != 0u)
        {
            const uint32_t count = std::min(m_vif1DirectBytesRemaining, sizeBytes - pos);
            m_vif1DirectBuffer.insert(m_vif1DirectBuffer.end(), data + pos, data + pos + count);
            pos += count;
            m_vif1DirectBytesRemaining -= count;
            if (m_vif1DirectBytesRemaining != 0u)
                continue;

            const uint8_t *payload = m_vif1DirectBuffer.data();
            const uint32_t payloadBytes = static_cast<uint32_t>(m_vif1DirectBuffer.size());
            uint32_t offset = 0u;
            if (m_vif1PendingPath2ImageQwc != 0u)
            {
                const uint32_t chunkQw = std::min(m_vif1PendingPath2ImageQwc, payloadBytes / 16u);
                std::vector<uint8_t> imagePacket(16u + static_cast<size_t>(chunkQw) * 16u, 0u);
                const uint64_t imageTag = static_cast<uint64_t>(chunkQw) |
                    ((m_vif1PendingPath2ImageQwc == chunkQw) ? (1ull << 15) : 0ull) |
                    (static_cast<uint64_t>(kGifFmtImage) << 58);
                std::memcpy(imagePacket.data(), &imageTag, sizeof(imageTag));
                std::memcpy(imagePacket.data() + 16u, payload, static_cast<size_t>(chunkQw) * 16u);
                submitGifPacket(GifPathId::Path2, imagePacket.data(),
                    static_cast<uint32_t>(imagePacket.size()), true, m_vif1PendingPath2DirectHl);
                offset = chunkQw * 16u;
                m_vif1PendingPath2ImageQwc -= chunkQw;
            }
            if (offset < payloadBytes)
            {
                submitGifPacket(GifPathId::Path2, payload + offset, payloadBytes - offset,
                    true, m_vif1PendingPath2DirectHl);
                m_vif1PendingPath2ImageQwc = pendingGifImageQwc(payload + offset, payloadBytes - offset);
            }
            m_vif1DirectBuffer.clear();
            m_vif1PendingPath2DirectHl = false;
            continue;
        }
        if (pos + 4u > sizeBytes)
            break;

""" + vif[command:]
    direct = vif.index("        else if (opcode == VIF_DIRECT || opcode == VIF_DIRECTHL)", loop)
    unpack = vif.index("        else if ((opcode & 0x60) == 0x60)", direct)
    vif = vif[:direct] + """        else if (opcode == VIF_DIRECT || opcode == VIF_DIRECTHL)
        {
            m_vif1DirectBytesRemaining = (imm == 0u ? 65536u : static_cast<uint32_t>(imm)) * 16u;
            m_vif1DirectBuffer.clear();
            m_vif1PendingPath2DirectHl = (opcode == VIF_DIRECTHL);
            continue;
        }
""" + vif[unpack:]
    return vif, memory, header
