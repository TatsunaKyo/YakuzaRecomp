#!/usr/bin/env python3
"""Connect verified EE memory paths to native IPU transport and MPEG blocks."""


def adapt_ipu_faults(runtime):
    include = '#include "ps2_runtime.h"'
    catch = '    catch (const std::exception &)\n'
    if runtime.count(include) != 1 or runtime.count(catch) != 10:
        raise ValueError("Pinned runtime memory-fault handlers differ; reassess")
    runtime = runtime.replace(include, include + '\n#include "yakuza/ipu_bitstream.h"')
    return runtime.replace(catch, '    catch (const yakuza::NativeDeviceError&) { throw; }\n' + catch)


def adapt_ipu(memory):
    def replace(old, new):
        nonlocal memory
        if memory.count(old) != 1:
            raise ValueError("Pinned IPU memory adaptation no longer matches; reassess")
        memory = memory.replace(old, new)

    replace('#include "runtime/ps2_memory.h"', '''#include "runtime/ps2_memory.h"
#include "yakuza/ipu_bitstream.h"
namespace {
void writeIpuOutput(PS2Memory& memory, uint32_t address, std::span<const uint8_t, 16> bytes) {
    const bool scratch = (address & 0x80000000u) != 0;
    const uint32_t target = scratch ? (0x70000000u | (address & 0x3fffu)) : (address & 0x1fffffffu);
    if (!scratch && target > PS2_RAM_SIZE - 16)
        throw yakuza::IpuError("IPU output DMA destination is outside EE RAM");
    memory.write128(target, _mm_loadu_si128(reinterpret_cast<const __m128i*>(bytes.data())));
}
}
''')
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
    replace('    if (const uint8_t *vuMem = mapVuMemory(physAddr, sizeof(__m128i), vuOffset, vuLimit))', '''    if (physAddr == 0x10007000u) // IPU_OUT_FIFO
    {
        auto& ipu = yakuza::ipuFor(this);
        const auto bytes = ipu.output(m_ioRegisters, {m_rdram, PS2_RAM_SIZE});
        if (ipu.takeDmaCompletion()) completeDmacChannel(0x1000b400u, 4);
        return _mm_loadu_si128(reinterpret_cast<const __m128i*>(bytes.data()));
    }
    if (const uint8_t *vuMem = mapVuMemory(physAddr, sizeof(__m128i), vuOffset, vuLimit))''')
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
    # Keep one output writer for all MMIO/FIFO entry paths. It uses the normal
    # memory write API, including scratchpad mapping and modification tracking.
    arguments = 'm_ioRegisters, {m_rdram, PS2_RAM_SIZE})'
    completion = '        if (ipu.takeDmaCompletion()) completeDmacChannel(0x1000b400u, 4);'
    if memory.count(arguments) != 4 or memory.count(completion) != 4:
        raise ValueError("IPU entry path count differs; reassess")
    memory = memory.replace(arguments, '''m_ioRegisters, {m_rdram, PS2_RAM_SIZE},
            [this](uint32_t address, std::span<const uint8_t, 16> bytes) { writeIpuOutput(*this, address, bytes); })''')
    memory = memory.replace(completion, completion + '\n        if (ipu.takeOutputDmaCompletion()) completeDmacChannel(0x1000b000u, 3);')
    memory = memory.replace('(physAddr >= 0x1000b400u && physAddr < 0x1000b500u))',
        '(physAddr >= 0x1000b400u && physAddr < 0x1000b500u) ||\n        (physAddr >= 0x1000b000u && physAddr < 0x1000b100u))')
    memory = memory.replace('(address >= 0x1000b400u && address < 0x1000b500u))',
        '(address >= 0x1000b400u && address < 0x1000b500u) ||\n        (address >= 0x1000b000u && address < 0x1000b100u))')
    memory = memory.replace('address == 0x1000b400u && (value & 0x100u)',
        '(address == 0x1000b400u || address == 0x1000b000u) && (value & 0x100u)')
    return memory
