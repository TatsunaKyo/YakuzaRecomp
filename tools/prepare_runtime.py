#!/usr/bin/env python3
"""Build private PAL memory-layout, dispatch and syscall adaptations.

Keep the dependency checkout intact. Original game files and translated
instructions are never patched here.
"""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_game import require
from prepare_vif import adapt_vif
from prepare_vif_irq import adapt_flush_interrupts
from prepare_ipu import adapt_ipu, adapt_ipu_faults
from prepare_spr import adapt_spr
from prepare_mmi import adapt_mmi, MACROS_SHA256
from prepare_gif import adapt_path3_gif, GIF_ARBITER_SHA256

HASHES = {
    "Kernel/Syscalls/Helpers/State.h": "88a8a4b4991b87fe052a4d3555facbb355207dd8572eaa1ff978c1fc712bf6c4",
    "ps2_runtime.cpp": "77cd184f2e70eacfd5ea584ec95829553e3deeead0a19c04e4b0970dd7c6c9ee",
    "Kernel/Syscalls/Thread.cpp": "e73d7f0a46d07fc0f70d5b49b6453ed64271b3ad19ffd62a6a872095491bcdf4",
    "Kernel/EeScheduler.cpp": "89383df078a13e9d13335f158ce88f0fb85935c57f2edab0ef8f4a0c9edb4b83",
    "ps2_vif1_interpreter.cpp": "4090662ca7029c6563444e69ac184cf1396efdf672d179dd8e9d617fe856c4a5",
    "ps2_memory.cpp": "4bae084dfa6ea30479af5efde70c61927a4fe5a49216d99c3db76297db4ac22a",
}
MEMORY_HEADER_SHA256 = "9bba23a767b3ea0e3d7af5cf864b20aa730eb8ce4e07c005668ceb761527c770"


def replace(text, old, new, count=1):
    require(text.count(old) == count, "Pinned runtime adaptation no longer matches; reassess")
    return text.replace(old, new)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != data: path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    output = args.out_dir.resolve()
    require(not output.is_relative_to(project), "Keep adapted runtime output outside the checkout")
    source = args.runtime_dir.resolve() / "src/lib"
    require(not output.is_relative_to(args.runtime_dir.resolve()), "Keep the dependency checkout unchanged")
    layout = json.loads((project / "config/pal-runtime-layout.json").read_text())
    regions = [region for region in layout.values() if isinstance(region, dict)]
    regions.sort(key=lambda region: region["start"])
    previous = 0x80000  # Native kernel mirrors end here; PAL resident starts at 1 MiB.
    for region in regions:
        require(previous <= region["start"] < region["end"] <= 0x100000 and
                (region["start"] | region["end"]) % 16 == 0, "Overlapping or invalid native PAL memory regions")
        previous = region["end"]
    require(layout["game_heap_end"] == 0x1FE0000, "PAL heap must stop below its original 128 KiB main stack")
    texts = {}
    for name, expected in HASHES.items():
        data = (source / name).read_bytes().replace(b"\r\n", b"\n")
        require(hashlib.sha256(data).hexdigest() == expected, "Unsupported runtime source: " + name)
        texts[name] = data.decode()
    state = texts["Kernel/Syscalls/Helpers/State.h"]
    for name, old, key in (
        ("kRpcPacketPoolBase", "0x01F00000", "rpc_packets"),
        ("kRpcServerPoolBase", "0x01F10000", "rpc_servers"),
        ("kTlsPoolBase", "0x01F20000", "tls"),
        ("kBootModePoolBase", "0x01F30000", "boot_mode"),
    ):
        state = replace(state, f"{name} = {old};", f"{name} = 0x{layout[key]['start']:08x};")
    texts["Kernel/Syscalls/Helpers/State.h"] = state
    runtime = texts["ps2_runtime.cpp"]
    runtime = replace(runtime, "m_asyncCallbackStackFloor = std::min(kGuestHeapHardLimit, PS2_RAM_SIZE);",
                      f"m_asyncCallbackStackFloor = 0x{layout['callback_stacks']['start']:x}u;")
    runtime = replace(runtime, "m_asyncCallbackStackFloor = std::min(std::max(hardLimit, suggestedHeapBase), PS2_RAM_SIZE);",
                      f"m_asyncCallbackStackFloor = 0x{layout['callback_stacks']['start']:x}u;")
    runtime = replace(runtime, "m_asyncCallbackStackTop = PS2_RAM_SIZE;",
                      f"m_asyncCallbackStackTop = 0x{layout['callback_stacks']['end']:x}u;", 2)
    runtime = replace(runtime, "    const uint32_t entryPc = ctx->pc;\n", "")
    runtime = replace(runtime, """    if (ctx->pc == entryPc)
    {
        ctx->pc = fallthroughPc;
    }

""", """    // A recursive guest call may yield before re-entering this same address.
    // Only an explicit guest return to fallthroughPc completes a call. Native
    // SDK wrappers set PC to the caller before invoking their service.
""")
    texts["ps2_runtime.cpp"] = adapt_ipu_faults(runtime)
    thread = texts["Kernel/Syscalls/Thread.cpp"]
    thread = replace(thread, """            const int result = ee.changePriority(id, priority, interruptSafe, oldPriority);
            setReturnS32(ctx, result);
""", """            const int result = ee.changePriority(id, priority, interruptSafe, oldPriority);
            // The EE syscall returns the previous priority on success. SDK
            // critical sections save that value and restore it on exit.
            setReturnS32(ctx, result == 0 ? oldPriority : result);
""")
    thread = replace(thread, """        const int result = ee.resumeThread(static_cast<int>(getRegU32(ctx, 4)), false);
        setReturnS32(ctx, result);
""", """        const int id = static_cast<int>(getRegU32(ctx, 4));
        const int result = ee.resumeThread(id, false);
        // EE ResumeThread returns the target ID on success. The original
        // CRI frame loop checks that ID before waking its resumed worker.
        setReturnS32(ctx, result == 0 ? id : result);
""")
    thread = replace(thread, """            const int result = ee.wakeupThread(static_cast<int>(getRegU32(ctx, 4)), interruptSafe);
            setReturnS32(ctx, result);
""", """            const int id = static_cast<int>(getRegU32(ctx, 4));
            const int result = ee.wakeupThread(id, interruptSafe);
            // The EE wakeup ABI also returns the target ID. CRI only clears
            // its pending notification after that acknowledgement succeeds.
            setReturnS32(ctx, result == 0 ? id : result);
""")
    texts["Kernel/Syscalls/Thread.cpp"] = thread
    scheduler = texts["Kernel/EeScheduler.cpp"]
    scheduler = replace(scheduler, "    target->context = R5900Context{};\n", """    target->context = R5900Context{};
    // VF0 is the hardware constant (0,0,0,1), including on a fresh or
    // restarted thread. The generic context constructor zeroes its W lane.
    target->context.vu0_vf[0] = _mm_set_ps(1.0f, 0.0f, 0.0f, 0.0f);
""")
    texts["Kernel/EeScheduler.cpp"] = scheduler
    include = args.runtime_dir.resolve() / "include"
    memory_header = (include / "runtime/ps2_memory.h").read_bytes().replace(b"\r\n", b"\n")
    require(hashlib.sha256(memory_header).hexdigest() == MEMORY_HEADER_SHA256,
            "Unsupported runtime header: runtime/ps2_memory.h")
    texts["ps2_vif1_interpreter.cpp"], texts["ps2_memory.cpp"], memory_header = adapt_vif(
        texts["ps2_vif1_interpreter.cpp"], texts["ps2_memory.cpp"], memory_header.decode())
    texts["ps2_vif1_interpreter.cpp"], texts["ps2_memory.cpp"], texts["Kernel/EeScheduler.cpp"] = adapt_flush_interrupts(
        texts["ps2_vif1_interpreter.cpp"], texts["ps2_memory.cpp"], texts["Kernel/EeScheduler.cpp"])
    texts["ps2_memory.cpp"] = adapt_spr(adapt_ipu(texts["ps2_memory.cpp"]))
    texts["gs/ps2_gif_arbiter.cpp"] = adapt_path3_gif((source / "gs/ps2_gif_arbiter.cpp").read_bytes()).decode()
    # Copy the complete include tree so quoted sibling includes and PCHs see
    # the same adapted PS2Memory layout in every translation unit.
    for path in include.rglob("*"):
        require(not path.is_symlink(), "Unexpected symlink in pinned runtime headers")
        if not path.is_file(): continue
        relative = path.relative_to(include)
        data = memory_header.encode() if relative.as_posix() == "runtime/ps2_memory.h" else path.read_bytes()
        if relative.as_posix() == "ps2_runtime_macros.h":
            data = adapt_mmi(data)
        save(output / "include" / relative, data)
    for path in source.rglob("*"):
        require(not path.is_symlink(), "Unexpected symlink in pinned runtime source")
        if not path.is_file(): continue
        relative = path.relative_to(source)
        data = texts[relative.as_posix()].encode() if relative.as_posix() in texts else path.read_bytes()
        save(output / "src/lib" / relative, data)
    header = "#pragma once\nnamespace yakuza::pal_memory {\n"
    for key in ("native_heap", "callback_stacks"):
        for bound in ("start", "end"):
            header += f"inline constexpr unsigned {key}_{bound} = 0x{layout[key][bound]:x}u;\n"
    header += f"inline constexpr unsigned game_heap_end = 0x{layout['game_heap_end']:x}u;\n}}\n"
    save(output / "pal_runtime_layout.h", header.encode())
    save(output / "adaptation.json", (json.dumps({"source_sha256": HASHES,
        "gif_arbiter_sha256": GIF_ARBITER_SHA256,
        "memory_header_sha256": MEMORY_HEADER_SHA256, "macros_header_sha256": MACROS_SHA256,
        "layout": layout}, indent=2) + "\n").encode())
    print("Prepared private PAL runtime: heaps, recursive yields, syscall results, VIF and IPU input")


if __name__ == "__main__": main()
