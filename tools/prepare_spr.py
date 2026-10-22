#!/usr/bin/env python3
"""Adapt the pinned runtime's missing scratchpad source-chain transfers."""
def adapt_spr(memory):
    include='#include "runtime/ps2_memory.h"'
    old='''    const uint32_t mode = (chcr >> 2u) & 0x3u;
    if (mode != 0u)
        return false;

    const uint32_t qwc = m_ioRegisters[channelBase + 0x20u] & 0xFFFFu;'''
    if memory.count(include)!=1 or memory.count(old)!=1:
        raise ValueError("Pinned scratchpad DMA handler differs; reassess")
    memory=memory.replace(include,include+'\n#include "yakuza/scratchpad_dma.h"\n#include "yakuza/native_device_error.h"')
    return memory.replace(old,'''    const uint32_t mode = (chcr >> 2u) & 0x3u;
    if (mode == 1u && channelBase == kSprToChannel)
    {
        yakuza::runScratchpadSourceChain(chcr, m_ioRegisters,
            {m_rdram, PS2_RAM_SIZE}, {m_scratchpad, PS2_SCRATCHPAD_SIZE},
            [this](uint32_t offset, std::span<const uint8_t,16> bytes) {
                write128(0x70000000u | offset,
                    _mm_loadu_si128(reinterpret_cast<const __m128i*>(bytes.data())));
            });
        completeDmacChannel(channelBase, 9u);
        return true;
    }
    if (mode != 0u)
        throw yakuza::NativeDeviceError("Scratchpad DMA destination chains/interleave are not implemented");

    const uint32_t qwc = m_ioRegisters[channelBase + 0x20u] & 0xFFFFu;''')
