#!/usr/bin/env python3
"""Recover the actual resident/MAIN registrations from the retained Windows PE."""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
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
MAIN_ROUTINE = (0x19f220, 0x19f2e0)
MAIN_ROUTINE_SHA256 = "0c9a48abefa3a73c8c84471a2a037fdc6bacbd5a29e602863fd0a48cbdd94ffe"


def recover(executable, disc_dir):
    require(hashlib.sha256(executable).hexdigest() == EXE_SHA256,
            "Executable differs from the verified private callback package")
    originals = {name: (disc_dir / name).read_bytes() for name in ("SLES_541.71", "MAIN.BIN")}
    for name, data in originals.items():
        require(hashlib.sha256(data).hexdigest() == PAL_INPUTS[name],
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
    first, end = MAIN_ROUTINE
    native = int(base_entries[hex(first)], 16)
    name, guest = result["base"]["native_owners"][hex(native)]
    require((name, guest) == ("FUN_0019f220", hex(first)), "Unexpected native owner for the truncated routine")
    native_code = pe.read(native, pe.base + unwind_ends[native - pe.base] - native, 0x20000000)
    # The exact old Debug PE stores guest PCs in R5900Context::pc at +0x200.
    # The terminal direct jump records its destination, and its NOP needs no store.
    pc_stores = re.findall(rb"\xc7[\x80-\x87]\x00\x02\x00\x00(.{4})", native_code, re.S)
    pcs = {struct.unpack("<I", value)[0] for value in pc_stores}
    require(pcs == set(range(first, end - 4, 4)) | {0x19f1d0},
            "The previous native routine does not verify the complete MAIN extent")
    original = originals["MAIN.BIN"][first - 0x167c00:end - 0x167c00]
    require(hashlib.sha256(original).hexdigest() == MAIN_ROUTINE_SHA256 and
            struct.unpack_from("<II", original, len(original) - 8) == (0x08067c74, 0),
            "Original MAIN routine bytes, jump or delay slot differ")
    return {
        "format": "yakuza-recovered-resident-catalog/v1",
        "executable_sha256": EXE_SHA256,
        "original_input_sha256": {name: PAL_INPUTS[name] for name in ("SLES_541.71", "MAIN.BIN")},
        "effective_registration_order": "base wins for colliding slots",
        "effective_entries": 332468,
        "overlapping_entries": len(base_entries.keys() & supplement_entries.keys()),
        "historical_instruction_coverage_verified": False,
        "historical_generated_source_bytes_verified": False,
        "verified_main_extent": {
            "start": hex(first), "end_exclusive": hex(end),
            "native_owner": hex(native), "guest_pc_stores": len(pcs) - 1,
            "original_sha256": MAIN_ROUTINE_SHA256,
        },
        **result,
    }


def restore_boot_extent(text):
    first, end = MAIN_ROUTINE
    reader = csv.DictReader(io.StringIO(text))
    require(reader.fieldnames == ["Name", "Start", "End", "Size"], "Unexpected decoded map header")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    changed, previous = 0, 0
    for row in reader:
        lo, hi = int(row["Start"], 0), int(row["End"], 0)
        if lo == first:
            require(row["Name"] == "FUN_0019f220" and hi == first + 4 and row["Size"] == "4",
                    "Decoded map does not contain the verified truncated routine")
            hi = end
            row.update(End=hex(hi), Size=str(hi - lo))
            changed += 1
        require(previous <= lo < hi and (lo | hi) % 4 == 0 and int(row["Size"]) == hi - lo,
                "Invalid or overlapping decoded ranges")
        writer.writerow(row)
        previous = hi
    require(changed == 1, "Missing unique MAIN routine to restore")
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-exe", type=Path, required=True)
    parser.add_argument("--disc-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--decoded-map", type=Path)
    parser.add_argument("--out-decoded-map", type=Path)
    args = parser.parse_args()
    require(bool(args.decoded_map) == bool(args.out_decoded_map), "Specify both decoded map paths")
    project = Path(__file__).resolve().parents[1]
    require(all(not path.resolve().is_relative_to(project) for path in (args.out, args.out_decoded_map) if path),
            "Keep the private native catalog outside the checkout")
    result = recover(args.previous_exe.read_bytes(), args.disc_dir)
    if args.out_decoded_map:
        restored = restore_boot_extent(args.decoded_map.read_text())
        write_new(args.out_decoded_map, restored.encode())
    write_new(args.out, (json.dumps(result, separators=(",", ":")) + "\n").encode())
    print(f"Recovered {result['effective_entries']} effective resident/MAIN registrations "
          f"with {result['overlapping_entries']} shared slots")


if __name__ == "__main__":
    main()
