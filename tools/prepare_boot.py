#!/usr/bin/env python3
"""Adapt verified private registration output to the full PAL address range.

No game code is embedded here. The original registrations stay intact, and empty
overlay slots remain unresolved until real overlay integration supplies them.
"""
import argparse
import json
from pathlib import Path
import re

from prepare_game import require


def dispatch_addresses(text):
    base = re.search(r'g_ps2RecompiledFunctionTableBase = (0x[0-9a-f]+)u;', text)
    require(base is not None, "Missing dispatch table base")
    address = int(base.group(1), 16)
    result = set()
    for slot, target in re.findall(
            r'g_ps2RecompiledFunctionTable\[(\d+)\] = \w+; // (0x[0-9a-f]+)', text):
        target = int(target, 16)
        require(target == address + int(slot) * 4 and target not in result,
                "Inconsistent or repeated dispatch registration")
        result.add(target)
    require(bool(result), "Empty dispatch registration")
    return result


def extend_table(text: str) -> str:
    base = re.search(r'g_ps2RecompiledFunctionTableBase = (0x[0-9a-f]+)u;', text)
    require(base is not None, "Unexpected upstream registration format")
    address = int(base.group(1), 16)
    require(address == 0x100008, "Not the supported PAL resident registration")
    end = 0x6EF500
    count = (end - address) // 4
    text, n = re.subn(r'g_ps2RecompiledFunctionTableEnd = 0x[0-9a-f]+u;',
                     f'g_ps2RecompiledFunctionTableEnd = 0x{end:x}u;', text)
    require(n == 1, "Missing function-table end")
    text, n = re.subn(r'g_ps2RecompiledFunctionTableSlotCount = \d+u;',
                     f'g_ps2RecompiledFunctionTableSlotCount = {count}u;', text)
    require(n == 1, "Missing function-table size")
    text, n = re.subn(r'g_ps2RecompiledFunctionTable\[\d+u\] = \{\};',
                     f'g_ps2RecompiledFunctionTable[{count}u] = {{}};', text)
    require(n == 1, "Missing function-table storage")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--supplement-dir", type=Path)
    args = parser.parse_args()
    require(not args.out_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
            "Keep generated game code outside the checkout")
    text = extend_table((args.generated_dir / "register_functions.cpp").read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "register_boot.cpp"
    if not path.exists() or path.read_text() != text: path.write_text(text)
    supplement = '#include "ps2_runtime.h"\n#include <stdexcept>\n#include <algorithm>\n#include <array>\n'
    if args.supplement_dir:
        folder = args.supplement_dir.resolve()
        require((folder / "register_functions.cpp").is_file(), "Missing supplemental registration")
        collisions = sorted(dispatch_addresses(text) &
                            dispatch_addresses((folder / "register_functions.cpp").read_text()))
        supplement += '#include ' + json.dumps((folder / "ps2_recompiled_functions.h").as_posix()) + '\n'
        for name in ("Base", "End", "SlotCount", ""):
            supplement += f'#define g_ps2RecompiledFunctionTable{name} g_yakuzaSupplementTable{name}\n'
        supplement += '#include ' + json.dumps((folder / "register_functions.cpp").as_posix()) + '\n'
        for name in ("Base", "End", "SlotCount", ""):
            supplement += f'#undef g_ps2RecompiledFunctionTable{name}\n'
        supplement += f'constexpr std::array<uint32_t, {len(collisions)}> baseline_entries{{{{' + \
            ', '.join(hex(address) + 'u' for address in collisions) + '}};\n'
        supplement += '''namespace yakuza {
void install_boot_supplement(PS2Runtime& runtime) {
    for (uint32_t i = 0; i < g_yakuzaSupplementTableSlotCount; ++i) {
        auto function = g_yakuzaSupplementTable[i];
        if (!function) continue;
        uint32_t address = g_yakuzaSupplementTableBase + i * 4;
        // Newly classified entries can share decoded bytes with an old chunk.
        // Keep every original mapping, including previously installed SDK hooks.
        if (runtime.hasFunction(address) &&
            std::binary_search(baseline_entries.begin(), baseline_entries.end(), address)) continue;
        if (runtime.hasFunction(address) || !runtime.replaceFunction(address, function))
            throw std::runtime_error("Supplement conflicts with the original dispatch map");
    }
}
}
'''
    else:
        supplement += 'namespace yakuza { void install_boot_supplement(PS2Runtime&) {} }\n'
    path = args.out_dir / "boot_supplement.cpp"
    if not path.exists() or path.read_text() != supplement: path.write_text(supplement)
    print("Prepared PAL boot registration; unpopulated overlays remain missing")


if __name__ == "__main__": main()
