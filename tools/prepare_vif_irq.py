"""Adapt observed VIF1 interrupting flush barriers and EE cause delivery.

The caller verifies complete pinned sources first. No runtime class layout or
original command words change. Other interrupting VIF opcodes retain their
existing behavior and are not covered by this flush-barrier adaptation.
"""
from prepare_game import require


def once(text, old, new):
    require(text.count(old) == 1, "Pinned VIF1 interrupt adaptation differs; reassess")
    return text.replace(old, new)


def adapt_flush_interrupts(vif, memory, scheduler):
    start = vif.index("void PS2Memory::processVIF1Data(const uint8_t *data, uint32_t sizeBytes)")
    prefix, body = vif[:start], vif[start:]
    body = once(body, "    uint32_t pos = 0;\n", """    // VIS retains commands arriving behind an interrupting flush. The EE
    // handler reads MARK before acknowledging STC; later MARKs cannot run yet.
    if ((vif1_regs.stat & (1u << 10)) != 0u)
    {
        m_vif1PendingCommandBytes.insert(m_vif1PendingCommandBytes.end(), data, data + sizeBytes);
        return;
    }
    uint32_t pos = 0;
""")
    body = once(body, """        else if (opcode == VIF_FLUSHE || opcode == VIF_FLUSH || opcode == VIF_FLUSHA)
        {
            continue;
        }
""", """        else if (opcode == VIF_FLUSHE || opcode == VIF_FLUSH || opcode == VIF_FLUSHA)
        {
            // VU and GIF operations above are synchronous in this host. The
            // completed flush now raises the actual VIF1 interrupt and stalls
            // until the original handler writes FBRST.STC.
            if (irq)
            {
                vif1_regs.stat |= (1u << 10); // VIS; INT was latched at decode.
                m_ioRegisters[0x1000F000u] |= (1u << 5); // INTC_STAT.VIF1.
                m_vif1PendingCommandBytes.assign(data + pos, data + sizeBytes);
                m_vif1PendingCommandDecoded = false;
                break;
            }
            continue;
        }
""")
    memory = once(memory, """    m_ioRegisters[address] = value;

    if (address >= 0x10003C00u && address < 0x10003E00u)
""", """    if (address == 0x1000F000u) // INTC_STAT is write-one-to-clear.
    {
        m_ioRegisters[address] &= ~(value & 0x7FFFu);
        return true;
    }
    m_ioRegisters[address] = value;

    if (address >= 0x10003C00u && address < 0x10003E00u)
""")
    memory = once(memory, """            if (value & 0x8u) // STC
            {
                vif1_regs.stat &= ~((1u << 8) | (1u << 9) | (1u << 10) | (1u << 11) | (1u << 12) | (1u << 13));
            }
""", """            if (value & 0x8u) // STC
            {
                const bool resumeInterrupt = (vif1_regs.stat & (1u << 10)) != 0u;
                vif1_regs.stat &= ~((1u << 8) | (1u << 9) | (1u << 10) | (1u << 11) | (1u << 12) | (1u << 13));
                if (resumeInterrupt && !m_vif1PendingCommandBytes.empty())
                {
                    auto commands = std::move(m_vif1PendingCommandBytes);
                    m_vif1PendingCommandBytes.clear();
                    m_vif1PendingCommandDecoded = false;
                    processVIF1Data(commands.data(), static_cast<uint32_t>(commands.size()));
                }
            }
""")
    read_start = memory.index("uint32_t PS2Memory::readIORegister(uint32_t address)")
    memory_prefix, reads = memory[:read_start], memory[read_start:]
    reads = once(reads, "    auto it = m_ioRegisters.find(address);\n", """    // Commands update the live register bank, not the CPU write shadow.
    // In particular, an EE interrupt handler must see the current MARK/MRK.
    if ((address >= 0x10003800u && address < 0x10003A00u) ||
        (address >= 0x10003C00u && address < 0x10003E00u))
    {
        const bool vif1 = address >= 0x10003C00u;
        const auto &regs = vif1 ? vif1_regs : vif0_regs;
        const uint32_t offset = address - (vif1 ? 0x10003C00u : 0x10003800u);
        switch (offset)
        {
        case 0x00u: return regs.stat;
        case 0x10u: return regs.fbrst;
        case 0x20u: return regs.err;
        case 0x30u: return regs.mark;
        case 0x40u: return regs.cycle;
        case 0x50u: return regs.mode;
        case 0x60u: return regs.num;
        case 0x70u: return regs.mask;
        case 0x80u: return regs.code;
        case 0x90u: return regs.itops;
        case 0xA0u: return regs.base;
        case 0xB0u: return regs.ofst;
        case 0xC0u: return regs.tops;
        case 0xD0u: return regs.itop;
        case 0xE0u: return regs.top;
        default:
            if ((offset & 0xFu) == 0u && offset >= 0x100u && offset <= 0x130u)
                return regs.row[(offset - 0x100u) >> 4];
            if ((offset & 0xFu) == 0u && offset >= 0x140u && offset <= 0x170u)
                return regs.col[(offset - 0x140u) >> 4];
            return 0u;
        }
    }

    auto it = m_ioRegisters.find(address);
""")
    memory = memory_prefix + reads
    scheduler = once(scheduler, """bool EeScheduler::checkpointDue(uint32_t cycles) noexcept
{
    accountCycles(cycles);
""", """bool EeScheduler::checkpointDue(uint32_t cycles) noexcept
{
    accountCycles(cycles);
    if ((m_enabledIntcMask & (1u << 5)) != 0u &&
        (m_runtime.memory().readIORegister(0x1000F000u) & (1u << 5)) != 0u)
    {
        m_checkpointPending.store(true, std::memory_order_release);
    }
""")
    scheduler = once(scheduler, """    assertExecutor();
    processDueDeadlines();
    const uint32_t timerInterrupts = m_pendingEeTimerInterrupts;
""", """    assertExecutor();
    processDueDeadlines();
    // HLE kernel delivery acknowledges the INTC latch, then uses the same
    // queued guest invocation path as the existing timer and DMA handlers.
    // Keep the latch pending while the cause is disabled.
    if ((m_enabledIntcMask & (1u << 5)) != 0u &&
        (m_runtime.memory().readIORegister(0x1000F000u) & (1u << 5)) != 0u)
    {
        m_runtime.memory().writeIORegister(0x1000F000u, 1u << 5);
        dispatchIrq(false, 5u);
    }
    const uint32_t timerInterrupts = m_pendingEeTimerInterrupts;
""")
    scheduler = once(scheduler, """    case EeEventType::VBlankStart:
        ++m_vsyncTick;
""", """    case EeEventType::VBlankStart:
        // The real scheduled edge also feeds guest code polling INTC_STAT.
        m_runtime.memory().m_ioRegisters[0x1000F000u] |= (1u << 2);
        ++m_vsyncTick;
""")
    scheduler = once(scheduler, """    case EeEventType::VBlankEnd:
        dispatchIrq(false, 3u);
""", """    case EeEventType::VBlankEnd:
        m_runtime.memory().m_ioRegisters[0x1000F000u] |= (1u << 3);
        dispatchIrq(false, 3u);
""")
    return prefix + body, memory, scheduler
