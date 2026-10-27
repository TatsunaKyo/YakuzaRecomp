#!/usr/bin/env python3
"""Checked RPC thread scheduling and PCM AutoDMA clock for private IOP sources."""
import hashlib

PINNED = {
    "emulator/core/iop_kernel.h": "260863c946a687faf5e88c309615de4da319a3028124a97b714468dbf6df0ab5",
    "emulator/services/iop_rpc.h": "bddd5dbe9cebfcb4214b0b5f09fff210e8399a5710105b3f2d4600c5bc38fae1",
    "emulator/services/iop_rpc.cpp": "62680a58200046de70babc31273535c51fa43a1979e0ffde5c307481dc83c969",
    "emulator/core/iop_memory.cpp": "3952624ce32b501511a7460a7ce6d387f314d7173e8a6f4a2ed7fc1507e5f4ee",
}


def replace_once(data, old, new):
    if data.count(old) != 1:
        raise ValueError("Pinned IOP RPC boundary no longer matches: " + old[:90].decode())
    return data.replace(old, new)


RPC_EXECUTION = b'''
        uint32_t executeGuestRpcFunction(int threadId, uint32_t address,
                                         uint32_t a0, uint32_t a1, uint32_t a2,
                                         uint32_t a3, uint32_t gp) override
        {
            // Queueless/polled services retain the executor's existing call path.
            if (threadId <= 0)
                return callFunction(address, a0, a1, a2, a3, gp);
            if (activeCpu)
                throw std::runtime_error("IOP RPC cannot replace an active guest CPU");
            IopThread *thread = kernel.findThread(threadId);
            if (!thread)
                throw std::runtime_error("IOP RPC queue refers to a missing server thread");
            const uint64_t startInstructions = totalInstructions, startCycles = totalCycles;
            const auto advance = [&]() {
                // The existing call guard also bounds queued dispatch and waits.
                if (totalInstructions - startInstructions >= kMaxCallInstructions ||
                    totalCycles - startCycles >= kMaxCallInstructions)
                {
                    std::ostringstream message;
                    message << "IOP RPC server thread did not complete within its call budget: thread="
                            << threadId << " entry=0x" << std::hex << address << " pc=0x" << thread->cpu.pc
                            << " state=" << unsigned(thread->state) << " priority=" << thread->priority
                            << " interrupt_control=" << memory.interruptControl()
                            << " adma0=" << memory.read16(0x1f9001b0u)
                            << " adma1=" << memory.read16(0x1f9005b0u);
                    throw std::runtime_error(message.str());
                }
                const uint64_t remaining = std::min<uint64_t>(
                    kMaxCallInstructions - (totalInstructions - startInstructions),
                    kMaxCallInstructions - (totalCycles - startCycles));
                runCycles(std::min<uint64_t>(kDefaultSlice, remaining));
                if (kernel.findThread(threadId) != thread)
                    throw std::runtime_error("IOP RPC server thread was deleted during dispatch");
            };
            // A registered thread can still be finishing initialization on arrival.
            while (thread->state != IopThreadState::Sleep)
            {
                if (thread->state == IopThreadState::Dormant || thread->state == IopThreadState::Dead)
                    throw std::runtime_error("IOP RPC server thread is not in its service loop");
                advance();
            }
            const IopCpuState serviceLoop = thread->cpu;
            const uint32_t stack = serviceLoop.gpr[29];
            if (stack < thread->stackBase + 32u || stack > thread->stackBase + thread->stackSize ||
                !memory.ownsRamRange(stack - 32u, 32u))
                throw std::runtime_error("IOP RPC server stack is outside its thread allocation");
            thread->cpu = {};
            thread->cpu.pc = address;
            thread->cpu.gpr[4] = a0; thread->cpu.gpr[5] = a1;
            thread->cpu.gpr[6] = a2; thread->cpu.gpr[7] = a3;
            thread->cpu.gpr[28] = gp;
            thread->cpu.gpr[29] = (stack - 32u) & ~15u;
            thread->cpu.gpr[31] = kCallReturnSentinel;
            thread->state = IopThreadState::Ready;
            // Only the normal scheduler chooses execution order. In particular,
            // a lower-priority RPC cannot interrupt an unmasked audio work item.
            while (thread->cpu.pc != kCallReturnSentinel)
            {
                if (thread->cpu.stopped || thread->state == IopThreadState::Dead ||
                    thread->state == IopThreadState::Dormant)
                    throw std::runtime_error("IOP RPC server stopped before returning");
                advance();
            }
            if (memory.interruptControl() == 0u)
                throw std::runtime_error("IOP RPC server returned with interrupts masked");
            const uint32_t result = thread->cpu.gpr[2];
            // Return to the host implementation of RpcLoop only after a real
            // guest return. Failed/panicking callbacks keep their diagnostic state.
            thread->cpu = serviceLoop;
            thread->state = IopThreadState::Sleep;
            return result;
        }
'''


def prepare(source_dir, emulator, kernel):
    files = {}
    for name, expected in PINNED.items():
        data = (source_dir / "src" / name).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Unsupported pinned IOP RPC source: " + name)
        files[name] = data
    name = "emulator/core/iop_kernel.h"
    files[name] = replace_once(files[name], b"        void cleanupDeadThreads();",
        b"        [[nodiscard]] IopThread *findThread(int id) noexcept;\n        void cleanupDeadThreads();")
    kernel = replace_once(kernel, b"    void IopKernel::cleanupDeadThreads()",
        b"    IopThread *IopKernel::findThread(int id) noexcept\n    {\n"
        b"        const auto it = m_threads.find(id);\n"
        b"        return it == m_threads.end() ? nullptr : &it->second;\n    }\n\n"
        b"    void IopKernel::cleanupDeadThreads()")
    name = "emulator/services/iop_rpc.h"
    files[name] = replace_once(files[name], b"        [[nodiscard]] virtual uint32_t executeGuestFunctionWithBudget(",
        b"        [[nodiscard]] virtual uint32_t executeGuestRpcFunction(int threadId, uint32_t address,\n"
        b"            uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t gp)\n        {\n"
        b"            (void)threadId;\n            return executeGuestFunction(address, a0, a1, a2, a3, gp);\n        }\n"
        b"        [[nodiscard]] virtual uint32_t executeGuestFunctionWithBudget(")
    name = "emulator/services/iop_rpc.cpp"
    files[name] = replace_once(files[name],
        b"        case 19: // SetRpcQueue\n            setV0(cpu.gpr[4]);",
        b"        case 19: // SetRpcQueue\n"
        b"            if (m_memory.ownsRamRange(cpu.gpr[4], 24u))\n            {\n"
        b"                m_memory.write32(cpu.gpr[4], cpu.gpr[5]);\n"
        b"                for (uint32_t offset = 4u; offset < 24u; offset += 4u)\n"
        b"                    m_memory.write32(cpu.gpr[4] + offset, 0u);\n            }\n"
        b"            setV0(cpu.gpr[4]);")
    files[name] = replace_once(files[name],
        b"        uint32_t returnPointer = executor.executeGuestFunction(server.function,",
        b"        const int threadId = server.queue != 0u && m_memory.ownsRamRange(server.queue, 24u)\n"
        b"            ? static_cast<int32_t>(m_memory.read32(server.queue)) : 0;\n"
        b"        uint32_t returnPointer = executor.executeGuestRpcFunction(threadId, server.function,")
    name = "emulator/core/iop_memory.cpp"
    files[name] = replace_once(files[name],
        b"        m_dmaStart = DmaStart{\n",
        b"        // PCM16 AutoDMA consumes one 32-bit stereo frame per 48 kHz\n"
        b"        // sample tick (36,864,000 / 48,000 = 768 IOP cycles).\n"
        b"        // Its completion follows input consumption rather than bus speed.\n"
        b"        const uint32_t autoDma = read16(0x1F9001B0u + (secondCore ? 0x400u : 0u));\n"
        b"        const bool pcmInput = (value & 1u) != 0u && (autoDma & (secondCore ? 2u : 1u)) != 0u;\n"
        b"        const uint64_t delay = pcmInput ? transferWords * 768u\n"
        b"                                        : std::max<uint64_t>(transferWords * 2u, 64u);\n"
        b"        m_dmaStart = DmaStart{\n")
    files[name] = replace_once(files[name],
        b"            std::max<uint64_t>(transferWords * 2u, 64u),", b"            delay,")
    emulator = replace_once(emulator, b"        uint32_t executeGuestFunctionWithBudget(",
        RPC_EXECUTION + b"\n        uint32_t executeGuestFunctionWithBudget(")
    files["emulator/iop_emulator.cpp"] = emulator
    files["emulator/core/iop_kernel.cpp"] = kernel
    return files
