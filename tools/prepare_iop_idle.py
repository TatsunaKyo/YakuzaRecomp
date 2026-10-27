#!/usr/bin/env python3
"""Cache the next event deadline only while the native IOP scheduler is idle."""
from prepare_iop_rpc import replace_once


def adapt_idle(data):
    data = replace_once(data, b"            eeCycleCarry = 0;",
                        b"            eeCycleCarry = 0;\n            idleUntilCycle = 0;")
    data = replace_once(data, b"        uint64_t eeCycleCarry = 0;",
                        b"        uint64_t eeCycleCarry = 0;\n        uint64_t idleUntilCycle = 0;")
    data = replace_once(data,
        b"            const uint32_t depth = callDepth++;",
        b"            idleUntilCycle = 0; // A guest call can wake or create threads/events.\n"
        b"            const uint32_t depth = callDepth++;")
    data = replace_once(data,
        b"            thread->state = IopThreadState::Ready;\n            // Only the normal scheduler",
        b"            idleUntilCycle = 0;\n"
        b"            thread->state = IopThreadState::Ready;\n            // Only the normal scheduler")
    data = replace_once(data,
        b"                while (totalCycles < target)\n                {\n                    servicePendingDmaInterrupts();",
        b"                while (totalCycles < target)\n                {\n"
        b"                    // No runnable CPU and no due event existed at the last\n"
        b"                    // idle boundary. Advance only within this caller's time\n"
        b"                    // budget, stopping at the same known event deadline.\n"
        b"                    if (memory.interruptControl() != 0u && idleUntilCycle > totalCycles)\n"
        b"                    {\n                        totalCycles = std::min(target, idleUntilCycle);\n"
        b"                        if (totalCycles == target)\n                            break;\n                    }\n"
        b"                    idleUntilCycle = 0;\n"
        b"                    servicePendingDmaInterrupts();")
    data = replace_once(data,
        b"                        uint64_t nextWake = kernel.nextWakeCycle(target);",
        b"                        uint64_t nextWake = kernel.nextWakeCycle(UINT64_MAX);")
    data = replace_once(data,
        b"                        nextWake = timrman.nextEventCycle(nextWake);\n"
        b"                        totalCycles = std::max(totalCycles + 1u, std::min(target, nextWake));",
        b"                        nextWake = timrman.nextEventCycle(nextWake);\n"
        b"                        if (memory.interruptControl() != 0u)\n"
        b"                            idleUntilCycle = nextWake;\n"
        b"                        totalCycles = std::max(totalCycles + 1u, std::min(target, nextWake));")
    for method in (b"writeMemory(uint32_t address, const void *source, size_t size)",
                   b"zeroMemory(uint32_t address, size_t size)"):
        entry = b"    bool IopEmulator::" + method + b"\n    {\n"
        data = replace_once(data, entry, entry + b"        m_impl->idleUntilCycle = 0;\n")
    return data
