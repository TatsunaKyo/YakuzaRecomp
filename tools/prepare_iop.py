#!/usr/bin/env python3
"""Prepare checked private IOP interrupt and critical-section adapters."""
from pathlib import Path
import argparse
import hashlib
import json

SOURCE_SHA256 = "01deb410d04f441be12adc68638846061f19759e007c36cdfcbe987796199d36"
KERNEL_SHA256 = "203c9949793be35f30583612db855544356d1ec1124b96fdf9377e4d321c1002"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iop-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    source_dir = args.iop_dir.resolve()
    output = args.out_dir.resolve()
    if output.is_relative_to(source_dir):
        parser.error("Keep adapted IOP output outside the pinned dependency checkout")
    data = (source_dir / "src/emulator/iop_emulator.cpp").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        parser.error("Unsupported IOP emulator source; reassess the pinned adaptation")
    old = b"if (servicingDmaInterrupts || pendingDmaInterrupts.empty())"
    if data.count(old) != 1:
        parser.error("Pinned IOP interrupt guard no longer matches")
    new = (b"// Retain due DMA interrupts while the IOP CPU masks interrupts.\n"
           b"            // They become deliverable after the outer critical section restores I_CTRL.\n"
           b"            if (servicingDmaInterrupts || pendingDmaInterrupts.empty() || memory.interruptControl() == 0u)")
    adapted = data.replace(old, new)
    callback = b"if (servicingGuestCallbacks || pendingGuestCallbacks.empty())"
    if data.count(callback) != 1:
        parser.error("Pinned IOP disc callback guard no longer matches")
    adapted = adapted.replace(callback,
        b"if (servicingGuestCallbacks || pendingGuestCallbacks.empty() || memory.interruptControl() == 0u)")
    timer = b"                    timrman.serviceDue(totalCycles, *this);"
    if data.count(timer) != 1:
        parser.error("Pinned IOP timer delivery boundary no longer matches")
    adapted = adapted.replace(timer,
        b"                    // Hardware timer handlers also wait for global interrupt restoration.\n"
        b"                    if (memory.interruptControl() != 0u)\n"
        b"                        timrman.serviceDue(totalCycles, *this);")
    imported = b"            if (const auto import = imports.decode(cpu.pc))\n            {\n"
    if data.count(imported) != 1:
        parser.error("Pinned IOP import entry no longer matches")
    adapted = adapted.replace(imported, imported +
        b"                // The import thunk consumes a pending load before its callee reads arguments.\n"
        b"                if (cpu.pendingLoad)\n                {\n"
        b"                    if (cpu.pendingLoadReg != 0u)\n"
        b"                        cpu.gpr[cpu.pendingLoadReg] = cpu.pendingLoadValue;\n"
        b"                    cpu.pendingLoad = false;\n                }\n")
    rpc = b"    RpcResult IopEmulator::handleRpc(const RpcRequest &request)\n    {\n"
    if data.count(rpc) != 1 or data.count(b"#include <algorithm>") != 1:
        parser.error("Pinned IOP RPC entry no longer matches")
    adapted = adapted.replace(b"#include <algorithm>", b"#include <algorithm>\n#include <stdexcept>")
    adapted = adapted.replace(rpc, rpc +
        b"        if (m_impl->rpc.hasServer(request.sid))\n        {\n"
        b"            const uint64_t start = m_impl->totalInstructions;\n"
        b"            while (m_impl->memory.interruptControl() == 0u)\n            {\n"
        b"                if (m_impl->activeCpu || m_impl->totalInstructions - start >= kMaxCallInstructions)\n"
        b"                    throw std::runtime_error(\"IOP RPC cannot resume the masked guest critical section\");\n"
        b"                const uint64_t before = m_impl->totalInstructions;\n"
        b"                m_impl->runCycles(1u);\n"
        b"                if (m_impl->totalInstructions == before)\n"
        b"                    throw std::runtime_error(\"IOP RPC is blocked by a guest critical section without a runnable thread\");\n"
        b"            }\n        }\n")
    kernel = (source_dir / "src/emulator/core/iop_kernel.cpp").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(kernel).hexdigest() != KERNEL_SHA256:
        parser.error("Unsupported IOP scheduler source; reassess the pinned adaptation")
    begin = b"    IopThread *IopKernel::beginNextReady(uint64_t currentCycle)\n    {\n"
    end = b"        else if (thread.state == IopThreadState::Running)\n            thread.state = IopThreadState::Ready;"
    if kernel.count(begin) != 1 or kernel.count(end) != 1:
        parser.error("Pinned IOP scheduler boundaries no longer match")
    kernel = kernel.replace(begin, begin +
        b"        // Resume a critical section split by the host execution budget.\n"
        b"        if (m_currentThread && m_currentThread->state == IopThreadState::Running)\n"
        b"            return m_currentThread;\n\n")
    kernel = kernel.replace(end,
        b"        else if (thread.state == IopThreadState::Running)\n        {\n"
        b"            // A host time slice is not a guest interrupt or a voluntary wait.\n"
        b"            if (m_memory.interruptControl() == 0u && !thread.cpu.yielded)\n                return;\n"
        b"            thread.state = IopThreadState::Ready;\n        }")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in (("iop_emulator.cpp", adapted), ("iop_kernel.cpp", kernel)):
        target = output / name
        if not target.exists() or target.read_bytes() != content:
            target.write_bytes(content)
    report = {"source_sha256": SOURCE_SHA256, "adapted_sha256": hashlib.sha256(adapted).hexdigest(),
              "kernel_sha256": KERNEL_SHA256, "adapted_kernel_sha256": hashlib.sha256(kernel).hexdigest(),
              "policy": "Preserve IOP critical sections across host slices, callbacks and RPC; consume import loads"}
    (output / "adaptation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Prepared private IOP interrupt and critical-section adaptations")


if __name__ == "__main__":
    main()
