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
