#!/usr/bin/env python3
"""Build a private PAL memory-layout adaptation of the pinned runtime.

Keep the dependency checkout intact. Only native helper addresses change;
original game files and translated instructions are never patched here.
"""
import argparse
import hashlib
import json
from pathlib import Path

from prepare_game import require

HASHES = {
    "Kernel/Syscalls/Helpers/State.h": "88a8a4b4991b87fe052a4d3555facbb355207dd8572eaa1ff978c1fc712bf6c4",
    "ps2_runtime.cpp": "77cd184f2e70eacfd5ea584ec95829553e3deeead0a19c04e4b0970dd7c6c9ee",
}


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
    texts["ps2_runtime.cpp"] = runtime
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
    save(output / "adaptation.json", (json.dumps({"source_sha256": HASHES, "layout": layout}, indent=2) + "\n").encode())
    print("Prepared private PAL runtime: separate native helpers and original game heap")


if __name__ == "__main__": main()
