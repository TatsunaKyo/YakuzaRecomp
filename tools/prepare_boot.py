#!/usr/bin/env python3
"""Adapt verified private registration output to the full PAL address range.

No game code is embedded here. The original registrations stay intact, and empty
overlay slots remain unresolved until real overlay integration supplies them.
"""
import argparse
from pathlib import Path
import re

from prepare_game import require


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
    args = parser.parse_args()
    require(not args.out_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
            "Keep generated game code outside the checkout")
    text = extend_table((args.generated_dir / "register_functions.cpp").read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / "register_boot.cpp"
    if not path.exists() or path.read_text() != text: path.write_text(text)
    print("Prepared PAL boot registration; unpopulated overlays remain missing")


if __name__ == "__main__": main()
