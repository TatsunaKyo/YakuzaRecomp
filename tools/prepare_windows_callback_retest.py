#!/usr/bin/env python3
"""Prepare a private A/B retest using the exact previous PAL Windows host.

Only the GAME descriptor's entry span is changed. The original sections and
translations are retained, and two normally recompiled return methods are
registered with the original GAME loader. This does not rebuild resident/MAIN.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct

from prepare_game import require, write_new
from recover_game_catalog import PE, recover


CALLBACKS = (0x69ff40, 0x69ff50)
# Verified -O2 Windows x64 code for both original JR $ra / NOP methods.
RETURN_LEAF = bytes.fromhex("8b 82 f0 01 00 00 89 82 00 02 00 00 c3")


def align(value, size):
    return (value + size - 1) & -size


def relocation_blocks(addresses):
    pages = defaultdict(list)
    for address in addresses:
        pages[address & ~0xfff].append(0xa000 | (address & 0xfff))
    output = bytearray()
    for page, entries in sorted(pages.items()):
        entries.sort()
        if len(entries) % 2:
            entries.append(0)
        output += struct.pack("<II", page, 8 + 2 * len(entries))
        output += struct.pack(f"<{len(entries)}H", *entries)
    return bytes(output)


def relocated_addresses(data):
    offset = 0
    addresses = set()
    while offset < len(data):
        require(len(data) - offset >= 8, "Truncated PE relocation block")
        page, size = struct.unpack_from("<II", data, offset)
        require(page % 4096 == 0 and 8 <= size <= len(data) - offset and size % 4 == 0,
                "Invalid PE relocation block")
        for (entry,) in struct.iter_unpack("<H", data[offset + 8:offset + size]):
            if entry:
                address = page + (entry & 0xfff)
                require(entry >> 12 == 10 and address not in addresses,
                        "Unexpected PE relocation type or duplicate address")
                addresses.add(address)
        offset += size
    return addresses


def prepare(previous, original_game, compiled_leaf):
    require(compiled_leaf == RETURN_LEAF, "Unexpected compiled Windows return method")
    catalog = recover(previous, original_game)
    pe = PE(previous)
    for address in CALLBACKS:
        offset = address - 0x62dc80
        require(original_game[offset:offset + 8] == bytes.fromhex("08 00 e0 03 00 00 00 00"),
                "Original GAME callback is not JR $ra / NOP")

    header = struct.unpack_from("<I", previous, 60)[0]
    optional = header + 24
    count = len(pe.sections)
    optional_size = struct.unpack_from("<H", previous, header + 20)[0]
    section_header = optional + optional_size + 40 * count
    image_size, headers_size = struct.unpack_from("<II", previous, optional + 56)
    virtual_alignment, file_alignment = struct.unpack_from("<II", previous, optional + 32)
    characteristics = struct.unpack_from("<H", previous, optional + 70)[0]
    security = struct.unpack_from("<II", previous, optional + 112 + 4 * 8)
    require((virtual_alignment, file_alignment) == (4096, 512) and
            characteristics & 0x40 and not characteristics & 0x4000 and security == (0, 0),
            "Unexpected image alignment, ASLR, Control Flow Guard or signature")
    require(section_header + 80 <= headers_size and previous[section_header:section_header + 80] == bytes(80),
            "No unused PE section headers")
    require(image_size == align(max(rva + size for _, rva, size, *_ in pe.sections), virtual_alignment),
            "Unexpected original image extent")

    descriptor, _ = pe.locate(catalog["programs_va"], 56)
    table_va, count = struct.unpack_from("<QQ", previous, descriptor + 40)
    rows = dict((addr, ptr) for addr, ptr in struct.iter_unpack("<I4xQ", pe.read(table_va, count * 16)))
    require(len(rows) == count and not rows.keys() & set(CALLBACKS), "GAME callback registration collision")

    code_rva = image_size
    data_rva = code_rva + virtual_alignment
    for address in CALLBACKS:
        rows[address] = pe.base + code_rva
    new_table = b"".join(struct.pack("<I4xQ", address, ptr) for address, ptr in sorted(rows.items()))
    reloc_directory = optional + 112 + 5 * 8
    reloc_rva, reloc_size = struct.unpack_from("<II", previous, reloc_directory)
    original_relocs = pe.read(pe.base + reloc_rva, reloc_size)
    old_addresses = relocated_addresses(original_relocs)
    require(catalog["programs_va"] - pe.base + 40 in old_addresses, "GAME descriptor pointer lacks ASLR relocation")
    new_addresses = {data_rva + offset for offset in range(8, len(new_table), 16)}
    require(max(old_addresses) < min(new_addresses), "Added relocations overlap the original image")
    new_relocs = original_relocs + relocation_blocks(new_addresses)
    require(relocated_addresses(new_relocs) == old_addresses | new_addresses, "Added PE relocations differ")

    out = bytearray(previous)
    sections = ((b".ykcode", code_rva, compiled_leaf, 0x60000020),
                (b".ykdata", data_rva, new_table + new_relocs, 0x40000040))
    for index, (name, rva, content, flags) in enumerate(sections):
        offset = align(len(out), file_alignment)
        raw_size = align(len(content), file_alignment)
        out += bytes(offset - len(out))
        out += content
        out += bytes(raw_size - len(content))
        struct.pack_into("<8s6I2HI", out, section_header + 40 * index,
                         name, len(content), rva, raw_size, offset, 0, 0, 0, 0, flags)
        size_field = optional + (4 if index == 0 else 8)
        old_size = struct.unpack_from("<I", out, size_field)[0]
        struct.pack_into("<I", out, size_field, old_size + raw_size)
    struct.pack_into("<H", out, header + 6, len(pe.sections) + len(sections))
    struct.pack_into("<I", out, optional + 56, align(data_rva + len(new_table) + len(new_relocs), virtual_alignment))
    struct.pack_into("<II", out, reloc_directory, data_rva + len(new_table), len(new_relocs))
    struct.pack_into("<QQ", out, descriptor + 40, pe.base + data_rva, len(rows))

    updated = PE(out)
    require(updated.sections[:len(pe.sections)] == pe.sections and updated.base == pe.base,
            "Original PE section layout changed")
    for _, _, _, size, offset, _ in pe.sections:
        if offset <= descriptor < offset + size:
            require(memoryview(out)[offset:descriptor + 40] == memoryview(previous)[offset:descriptor + 40] and
                    memoryview(out)[descriptor + 56:offset + size] == memoryview(previous)[descriptor + 56:offset + size],
                    "Original descriptor section changed outside the GAME span")
        else:
            require(memoryview(out)[offset:offset + size] == memoryview(previous)[offset:offset + size],
                    "An original PE section changed")
    require(updated.read(pe.base + code_rva, len(compiled_leaf), 0x20000000) == compiled_leaf and
            updated.read(pe.base + data_rva, len(new_table), 0x40000000) == new_table,
            "New native callback sections do not round-trip")
    proof = {
        "baseline_exe_sha256": hashlib.sha256(previous).hexdigest(),
        "retest_exe_sha256": hashlib.sha256(out).hexdigest(),
        "original_game_sha256": hashlib.sha256(original_game).hexdigest(),
        "retained_game_native_mappings": count,
        "new_game_mappings": [hex(address) for address in CALLBACKS],
        "total_game_native_mappings": len(rows),
        "new_aslr_relocations": len(new_addresses),
        "resident_main_host_rebuilt": False,
        "windows_game_execution_verified": False,
    }
    return out, proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-exe", required=True, type=Path)
    parser.add_argument("--original-game", required=True, type=Path)
    parser.add_argument("--compiled-leaf", required=True, type=Path, help="Raw .text from the compiled Win64 callback object")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    out = args.out_dir.resolve()
    require(not out.is_relative_to(Path(__file__).resolve().parents[1]), "Keep private binaries outside the checkout")
    patched, proof = prepare(args.previous_exe.read_bytes(), args.original_game.read_bytes(), args.compiled_leaf.read_bytes())
    write_new(out / "YakuzaRecomp-test.exe", patched)
    write_new(out / "callback-retest.json", (json.dumps(proof, indent=2) + "\n").encode())
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
