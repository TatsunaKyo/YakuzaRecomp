#!/usr/bin/env python3
"""Recover the actual resident/MAIN registrations from the retained Windows PE."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct

from prepare_game import PAL_INPUTS, require, write_new
from recover_game_catalog import EXE_SHA256, PE


INITIALIZERS = (
    ("base", "_GLOBAL__sub_I_register_boot.cpp", "g_ps2RecompiledFunctionTable", 330579),
    ("supplement", "_GLOBAL__sub_I_boot_supplement.cpp", "g_yakuzaSupplementTable", 3238),
)


def recover(executable, disc_dir):
    require(hashlib.sha256(executable).hexdigest() == EXE_SHA256,
            "Executable differs from the verified private callback package")
    for name in ("SLES_541.71", "MAIN.BIN"):
        require(hashlib.sha256((disc_dir / name).read_bytes()).hexdigest() == PAL_INPUTS[name],
                f"Unsupported original {name}")

    pe = PE(executable)
    symbols = pe.symbols()

    def symbol(name):
        matches = symbols.get(name, ())
        require(len(matches) == 1, f"Expected one PE symbol: {name}")
        return next(iter(matches))[0]

    def rip_target(address, opcode):
        code = pe.read(address, len(opcode) + 4, 0x20000000)
        require(code.startswith(opcode), "Unverified native initializer instruction")
        return address + len(code) + struct.unpack_from("<i", code, len(opcode))[0]

    pdata, = (section for section in pe.sections if section[0] == b".pdata")
    unwind_ends = {}
    for first, last, _ in struct.iter_unpack("<III", pe.read(pe.base + pdata[1], pdata[2])):
        require(first < last and first not in unwind_ends, "Invalid native unwind interval")
        unwind_ends[first] = last

    owners = defaultdict(set)
    for name, addresses in symbols.items():
        mangled = re.match(r"_Z(\d+)", name)
        if not mangled:
            continue
        end = mangled.end() + int(mangled[1])
        if name[end:] != "PhP12R5900ContextP10PS2Runtime":
            continue
        translated = re.fullmatch(r"(\w+)_0x([0-9a-f]+)", name[mangled.end():end])
        if translated:
            for address, _ in addresses:
                owners[address].add((translated[1], int(translated[2], 16)))

    result = {}
    for scope, initializer, table, expected in INITIALIZERS:
        entry = rip_target(symbol(initializer) + 4, b"\xe8")
        start = rip_target(entry + 11, b"\xe8")
        require(start - pe.base in unwind_ends, "Native initializer extent is unavailable")
        code = pe.read(start, pe.base + unwind_ends[start - pe.base] - start, 0x20000000)
        require(code[:5] == bytes.fromhex("50 48 89 0c 24") and code[-2:] == b"\x58\xc3" and
                len(code) == 7 + 14 * expected, "Native registration initializer differs")

        base, end, slots = (struct.unpack("<I", pe.read(symbol(table + field), 4))[0]
                            for field in ("Base", "End", "SlotCount"))
        table_va = symbol(table)
        require(end == base + 4 * slots, "Inconsistent native dispatch table bounds")
        entries, used_owners = {}, {}
        for offset in range(5, len(code) - 2, 14):
            first = start + offset
            native = rip_target(first, b"\x48\x8d\x05")
            slot = rip_target(first + 7, b"\x48\x89\x05") - table_va
            require(slot % 8 == 0 and 0 <= slot < slots * 8, "Native registration is outside the dispatch table")
            address = base + slot // 8 * 4
            matches = owners.get(native, ())
            require(len(matches) == 1 and native - pe.base in unwind_ends,
                    "Native registration has no unique translated owner")
            name, guest_owner = next(iter(matches))
            require(guest_owner <= address and guest_owner % 4 == 0 and
                    (0x100008 <= guest_owner <= address < 0x156280 or
                     0x167c40 <= guest_owner <= address < 0x592080) and address not in entries,
                    "Registration is not uniquely grounded in original resident/MAIN addresses")
            entries[address] = native
            used_owners[native] = (name, guest_owner)

        require(len(entries) == expected and
                all(entries.get(guest_owner) == native for native, (_, guest_owner) in used_owners.items()),
                "A translated native owner is absent from its own table")
        result[scope] = {
            "initializer_va": start,
            "native_owners": {hex(native): [name, hex(guest)] for native, (name, guest) in sorted(used_owners.items())},
            "entries": {hex(guest): hex(native) for guest, native in sorted(entries.items())},
        }

    base_entries = result["base"]["entries"]
    supplement_entries = result["supplement"]["entries"]
    require(len(base_entries.keys() | supplement_entries.keys()) == 332468,
            "Actual resident/MAIN dispatch union differs")
    return {
        "format": "yakuza-recovered-resident-catalog/v1",
        "executable_sha256": EXE_SHA256,
        "original_input_sha256": {name: PAL_INPUTS[name] for name in ("SLES_541.71", "MAIN.BIN")},
        "effective_registration_order": "base wins for colliding slots",
        "effective_entries": 332468,
        "overlapping_entries": len(base_entries.keys() & supplement_entries.keys()),
        "historical_instruction_coverage_verified": False,
        "historical_generated_source_bytes_verified": False,
        **result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-exe", type=Path, required=True)
    parser.add_argument("--disc-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require(not args.out.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
            "Keep the private native catalog outside the checkout")
    result = recover(args.previous_exe.read_bytes(), args.disc_dir)
    write_new(args.out, (json.dumps(result, separators=(",", ":")) + "\n").encode())
    print(f"Recovered {result['effective_entries']} effective resident/MAIN registrations "
          f"with {result['overlapping_entries']} shared slots")


if __name__ == "__main__":
    main()
