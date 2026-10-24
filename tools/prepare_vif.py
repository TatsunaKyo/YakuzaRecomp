"""Preserve VIF1 command and DIRECT / GIF IMAGE boundaries across deliveries."""
from prepare_game import require


def adapt_vif(vif, memory, header):
    anchor = "    uint32_t m_vif1PendingPath2ImageQwc = 0u;\n"
    require(header.count(anchor) == 1, "VIF state layout no longer matches")
    header = header.replace(anchor, anchor + """    uint32_t m_vif1DirectBytesRemaining = 0u;
    std::vector<uint8_t> m_vif1DirectBuffer;
    std::vector<uint8_t> m_vif1PendingCommandBytes;
    bool m_vif1PendingCommandDecoded = false;
""")
    for indent in ("    ", "                "):
        reset = indent + "m_vif1PendingPath2ImageQwc = 0u;\n"
        require(memory.count("\n" + reset) == 1, "VIF reset site no longer matches")
        memory = memory.replace("\n" + reset, "\n" + reset + indent +
            "m_vif1DirectBytesRemaining = 0u;\n" + indent + "m_vif1DirectBuffer.clear();\n" + indent +
            "m_vif1PendingCommandBytes.clear();\n" + indent + "m_vif1PendingCommandDecoded = false;\n")

    start = vif.index("void PS2Memory::processVIF1Data(const uint8_t *data, uint32_t sizeBytes)")
    loop = vif.index("    while (pos + 4 <= sizeBytes)", start)
    command = vif.index("        uint32_t cmd;", loop)
    vif = vif[:loop] + """    // A DMA/FIFO delivery can end inside a command word or its payload.
    // Keep the original bytes until that command can be consumed in full.
    std::vector<uint8_t> resumedBytes;
    const bool resumedCommandDecoded = m_vif1PendingCommandDecoded;
    if (!m_vif1PendingCommandBytes.empty())
    {
        resumedBytes = m_vif1PendingCommandBytes;
        resumedBytes.insert(resumedBytes.end(), data, data + sizeBytes);
        m_vif1PendingCommandBytes.clear();
        m_vif1PendingCommandDecoded = false;
        data = resumedBytes.data();
        sizeBytes = static_cast<uint32_t>(resumedBytes.size());
    }
    const auto retainCommand = [&](uint32_t start, bool decoded)
    {
        m_vif1PendingCommandBytes.assign(data + start, data + sizeBytes);
        m_vif1PendingCommandDecoded = decoded;
    };

    // DIRECT owns only its declared payload. A pending GIF IMAGE never
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
        {
            retainCommand(pos, false);
            break;
        }
        const uint32_t commandStart = pos;

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
    # Restrict substitutions to VIF1; VIF0 has its own parser and state.
    prefix, body = vif[:start], vif[start:]
    old = """        vif1_regs.code = cmd;
        vif1_regs.num = num;
        if (irq)
            vif1_regs.stat |= (1u << 11); // INT
"""
    require(body.count(old) == 1, "VIF1 command registers no longer match")
    body = body.replace(old, """        // An acknowledged IRQ must not be reasserted when only the
        // payload resumes: that command header was already decoded.
        if (!(resumedCommandDecoded && commandStart == 0u))
        {
            vif1_regs.code = cmd;
            vif1_regs.num = num;
            if (irq)
                vif1_regs.stat |= (1u << 11); // INT
        }
""")
    for count, expected in ((4, 1), (16, 2)):
        old = f"            if (pos + {count} > sizeBytes)\n                break;\n"
        require(body.count(old) == expected, "VIF1 register payload guards no longer match")
        body = body.replace(old, f"""            if (pos + {count} > sizeBytes)
            {{
                retainCommand(commandStart, true);
                break;
            }}
""")
    for anchor, length in (
        ("            const uint32_t mpgBytes = instructionCount * 8u;\n", "mpgBytes"),
        ("            totalBytes = (totalBytes + 3) & ~3u;\n", "totalBytes"),
    ):
        require(body.count(anchor) == 1, "VIF1 upload payload layout no longer matches")
        body = body.replace(anchor, anchor + f"""            if ({length} > sizeBytes - pos)
            {{
                retainCommand(commandStart, true);
                break;
            }}
""")
    vif = prefix + body
    return vif, memory, header
