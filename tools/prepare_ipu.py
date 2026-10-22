#!/usr/bin/env python3
"""Connect the verified runtime's EE memory paths to native IPU input state."""


def adapt_ipu(memory):
    def replace(old, new):
        nonlocal memory
        if memory.count(old) != 1:
            raise ValueError("Pinned IPU memory adaptation no longer matches; reassess")
        memory = memory.replace(old, new)

    replace('#include "runtime/ps2_memory.h"', '#include "runtime/ps2_memory.h"\n#include "yakuza/ipu_bitstream.h"')
    for signature in ('PS2Memory::~PS2Memory()', 'bool PS2Memory::initialize(size_t ramSize)'):
        replace(signature + '\n{', signature + '\n{\n    yakuza::releaseIpu(this);')
    replace('    // 64-bit IO read: compose from the two adjacent 32-bit IO register slots', '''    // IPU command DATA/BUSY and DMA state require the device handlers for LD.
    if ((physAddr >= 0x10002000u && physAddr < 0x10002040u) ||
        (physAddr >= 0x1000b400u && physAddr < 0x1000b500u))
        return uint64_t(readIORegister(physAddr)) | (uint64_t(readIORegister(physAddr + 4)) << 32);

    // 64-bit IO read: compose from the two adjacent 32-bit IO register slots''')
    replace('    if (!scratch && physAddr == 0x10004000u) // VIF0_FIFO', '''    if (!scratch && physAddr == 0x10007010u) // IPU_IN_FIFO
    {
        alignas(16) uint8_t bytes[16];
        _mm_storeu_si128(reinterpret_cast<__m128i*>(bytes), value);
        auto& ipu = yakuza::ipuFor(this);
        ipu.fifo(std::span<const uint8_t, 16>(bytes), m_ioRegisters, {m_rdram, PS2_RAM_SIZE});
        if (ipu.takeDmaCompletion()) completeDmacChannel(0x1000b400u, 4);
        return;
    }
    if (!scratch && physAddr == 0x10004000u) // VIF0_FIFO''')
    replace('''    if (address >= 0x10002000 && address <= 0x10002030)
    {
        if (address == 0x10002010)
        {
            m_ioRegisters[address] = value & ~(1u << 31);
            if (value & (1u << 30))
            {
                m_ioRegisters[0x10002000] = 0;
                m_ioRegisters[0x10002020] = 0;
                m_ioRegisters[0x10002030] = 0;
            }
        }
        else
        {
            m_ioRegisters[address] = value;
        }
        return true;
    }''', '''    if ((address >= 0x10002000u && address < 0x10002040u) ||
        (address >= 0x1000b400u && address < 0x1000b500u))
    {
        if (address == 0x1000b400u && (value & 0x100u))
            m_dmaStartCount.fetch_add(1, std::memory_order_relaxed);
        auto& ipu = yakuza::ipuFor(this);
        ipu.write(address, value, m_ioRegisters, {m_rdram, PS2_RAM_SIZE});
        if (ipu.takeDmaCompletion()) completeDmacChannel(0x1000b400u, 4);
        return true;
    }''')
    replace('''    if (address >= 0x10002000 && address <= 0x10002030)
    {
        uint32_t val = 0;
        switch (address)
        {
        case 0x10002000:
            val = m_ioRegisters[address];
            break;
        case 0x10002010:
            val = m_ioRegisters[address] & ~(1u << 31);
            break;
        case 0x10002020:
        case 0x10002030:
            val = m_ioRegisters[address];
            break;
        default:
            val = 0;
            break;
        }
        return val;
    }''', '''    if ((address >= 0x10002000u && address < 0x10002040u) ||
        (address >= 0x1000b400u && address < 0x1000b500u))
    {
        auto& ipu = yakuza::ipuFor(this);
        const auto value = ipu.read(address, m_ioRegisters, {m_rdram, PS2_RAM_SIZE});
        if (ipu.takeDmaCompletion()) completeDmacChannel(0x1000b400u, 4);
        return value;
    }''')
    return memory
