#!/usr/bin/env python3
"""Recover the actual PAL GAME catalog from the retained private callback PE.

Requires the original private files. Synthetic parser tests are not a substitute
for this recovery. Historical decoded coverage and C++ source bytes remain
unverified even when the native registration catalog is recovered successfully.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct

from overlay_image import SLOT_START, parse_overlay
from prepare_game import PAL_INPUTS, region, require, write_new

EXE_SHA256 = "fd515fc0922dea62a22b2c07f38ccca09e4810a548ef2470e7e139a0f197bd11"
GAME_SHA256 = "64b6d4f666a321e682be6becc6d89b37d6c171f0ff3448950a19e7c2ee590c37"
TABLE_SYMBOL = "_ZL17overlay_entries_0"
PROGRAMS_SYMBOL = "_ZZN6yakuza22compiled_boot_overlaysEvE8programs"
BOOT_SYMBOL = "_ZN6yakuza22compiled_boot_overlaysEv"


class PE:
    """Bounded PE32+/COFF reader; no execution, imports or relocations applied."""
    def __init__(self, data):
        self.data = data
        require(region(data, 0, 2, "DOS header") == b"MZ", "Not a PE file")
        at = struct.unpack("<I", region(data, 60, 4, "PE pointer"))[0]
        require(region(data, at, 4, "PE signature") == b"PE\0\0", "Invalid PE signature")
        machine, count, _, self.symbol_offset, self.symbol_count, optional_size, _ = struct.unpack(
            "<HHIIIHH", region(data, at + 4, 20, "COFF header"))
        require(machine == 0x8664 and 0 < count <= 96 and optional_size >= 112,
                "Expected an AMD64 PE32+ image")
        optional = region(data, at + 24, optional_size, "Optional header")
        require(struct.unpack_from("<H", optional)[0] == 0x20b, "Expected PE32+")
        self.base = struct.unpack_from("<Q", optional, 24)[0]
        self.sections = []
        for index in range(count):
            row = region(data, at + 24 + optional_size + index * 40, 40, "Section")
            name, virtual_size, rva, size, offset, _, _, _, _, flags = struct.unpack("<8s6I2HI", row)
            region(data, offset, size, "Section bytes")
            self.sections.append((name.rstrip(b"\0"), rva, virtual_size, size, offset, flags))

    def locate(self, va, size, flags=0):
        rva = va - self.base
        matches = [s for s in self.sections if s[1] <= rva and 0 <= size <= s[3] - (rva - s[1])]
        require(len(matches) == 1, "PE address is not uniquely file-backed")
        section = matches[0]
        require(section[5] & flags == flags, "PE address has incorrect section permissions")
        return section[4] + rva - section[1], section

    def read(self, va, size, flags=0):
        offset, _ = self.locate(va, size, flags)
        return region(self.data, offset, size, "PE virtual bytes")

    def symbols(self):
        require(0 < self.symbol_count <= 2000000, "Missing or excessive COFF symbols")
        start = self.symbol_offset
        region(self.data, start, self.symbol_count * 18, "COFF symbols")
        strings = start + self.symbol_count * 18
        length = struct.unpack("<I", region(self.data, strings, 4, "COFF string size"))[0]
        table = region(self.data, strings, length, "COFF strings")
        require(length >= 4, "Invalid COFF string table")
        result, index = defaultdict(set), 0
        while index < self.symbol_count:
            raw, value, section, kind, _, auxiliary = struct.unpack(
                "<8sIhHBB", region(self.data, start + index * 18, 18, "COFF symbol"))
            if raw[:4] == bytes(4):
                offset = struct.unpack_from("<I", raw, 4)[0]
                require(4 <= offset < length, "Invalid COFF symbol name offset")
                end = table.find(b"\0", offset)
                require(end >= 0, "Unterminated COFF symbol name")
                name = table[offset:end]
            else:
                name = raw.split(b"\0", 1)[0]
            if 1 <= section <= len(self.sections):
                text = name.decode("ascii")
                address = self.base + self.sections[section - 1][1] + value
                result[text].add((address, kind))
            require(index + auxiliary < self.symbol_count, "Invalid COFF auxiliary record count")
            index += 1 + auxiliary
        return result


def fingerprint(data):
    value = 0xcbf29ce484222325
    for byte in data:
        value = ((value ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return value


def recover(executable, image):
    require(hashlib.sha256(executable).hexdigest() == EXE_SHA256,
            "Executable differs from the verified private callback package")
    require(len(image) == 704896 and hashlib.sha256(image).hexdigest() == GAME_SHA256,
            "Original GAME image differs")
    layout = parse_overlay(image)
    pe = PE(executable)
    symbols = pe.symbols()
    require(all(name in symbols and len(symbols[name]) == 1
                for name in (TABLE_SYMBOL, PROGRAMS_SYMBOL, BOOT_SYMBOL)),
            "Required original catalog symbols are unavailable")
    programs = next(iter(symbols[PROGRAMS_SYMBOL]))[0]
    table = next(iter(symbols[TABLE_SYMBOL]))[0]
    boot = next(iter(symbols[BOOT_SYMBOL]))[0]
    # The known LLVM-MinGW/libc++ ABI has a 56-byte BootOverlay and 16-byte
    # NativeEntry. These offsets are checked against both native code and data.
    ident, pad1, name, name_size, size, pad2, original_fnv, entries, count = struct.unpack(
        "<IIQQIIQQQ", pe.read(programs, 56, 0x40000000))
    require(ident == 2 and pad1 == pad2 == 0 and size == len(image) and name_size == 8 and
            pe.read(name, name_size) == b"game.bin" and original_fnv == fingerprint(image),
            "Compiled GAME descriptor does not match verified original bytes")
    require(entries == table and count == 95309, "Compiled GAME span differs from the retained baseline")
    boot_code = pe.read(boot, 80, 0x20000000)
    references = []
    for at in range(len(boot_code) - 12):
        if boot_code[at:at + 3] != b"\x48\x8d\x15" or boot_code[at + 7] != 0xe8:
            continue
        target = boot + at + 7 + struct.unpack_from("<i", boot_code, at + 3)[0]
        if target != programs:
            continue
        constructor = boot + at + 12 + struct.unpack_from("<i", boot_code, at + 8)[0]
        constructor_names = [n for n, values in symbols.items() if any(a == constructor for a, _ in values)]
        require(any("span" in n and "BootOverlay" in n and "ILy1E" in n for n in constructor_names),
                "Boot accessor does not construct a one-overlay span")
        require(b"\x48\xc7\x40\x08\x01\x00\x00\x00" in pe.read(constructor, 48, 0x20000000),
                "Native span constructor does not retain its one-element size")
        references.append(boot + at)
    require(len(references) == 1, "Boot accessor reference to compiled GAME descriptor is unverified")
    raw = pe.read(table, count * 16, 0x40000000)
    _, table_section = pe.locate(table, len(raw))
    require(not table_section[5] & 0x80000000, "Compiled catalog is unexpectedly writable")
    functions = defaultdict(list)
    for mangled, values in symbols.items():
        match = re.match(r"_Z(\d+)", mangled)
        if not match:
            continue
        first = match.end()
        name = mangled[first:first + int(match[1])]
        suffix = re.search(r"_0x([0-9a-f]+)$", name)
        if name.startswith("game_") and suffix:
            for address, kind in values:
                if kind & 0x20:
                    functions[address].append((name, int(suffix[1], 16), mangled))
    records, owners, previous = [], {}, 0
    for offset in range(0, len(raw), 16):
        address, padding, native = struct.unpack_from("<IIQ", raw, offset)
        require(padding == 0 and address % 4 == 0 and previous < address and
                SLOT_START + 64 <= address < SLOT_START + len(image), "Invalid or duplicate GAME guest entry")
        pe.locate(native, 1, 0x20000000)
        require(len(functions[native]) == 1, "Native entry lacks a unique original GAME owner symbol")
        name, start, mangled = functions[native][0]
        require(start <= address and start % 4 == 0, "Original owner starts after its guest entry")
        owners[native - pe.base] = {"name": name, "guest_start": start, "mangled_symbol": mangled}
        records.append([address, native - pe.base])
        previous = address
    registered = {tuple(record) for record in records}
    require(len(owners) == 1983 and all((item["guest_start"], native) in registered
            for native, item in owners.items()), "Original GAME owner registration is incomplete")
    require(all(not ctor or any(address == ctor for address, _ in records) for ctor in layout.constructors),
            "Original GAME constructor registration is incomplete")
    table_offset, _ = pe.locate(table, len(raw))
    return {"format": "yakuza-recovered-game-catalog/v2", "executable_sha256": EXE_SHA256,
            "game_sha256": GAME_SHA256, "game_bytes": len(image), "game_fnv64": f"{original_fnv:016x}",
            "image_base": pe.base, "accessor_reference_va": references[0], "programs_va": programs,
            "table_va": table, "table_file_offset": table_offset,
            "table_sha256": hashlib.sha256(raw).hexdigest(), "entry_count": len(records),
            "owner_count": len(owners), "owners": owners, "entries": records,
            "historical_decoded_map": "unavailable; full old instruction coverage is unverified",
            "historical_generated_cpp": "unavailable; old source bytes are unverified"}


def callback_provenance(resident, main, image):
    for name, data in (("SLES_541.71", resident), ("MAIN.BIN", main)):
        require(hashlib.sha256(data).hexdigest() == PAL_INPUTS[name], "Original PAL input differs: " + name)
    require(hashlib.sha256(image).hexdigest() == GAME_SHA256, "Original GAME image differs")
    # MAIN is placed after the first resident LOAD's memory extent. Its MWo3
    # header's address field is not its actual load address.
    phoff = struct.unpack_from("<I", resident, 28)[0]
    load = struct.unpack("<8I", region(resident, phoff, 32, "Original resident LOAD"))
    main_address = load[2] + load[5]
    require(load[0] == 1 and main_address == 0x167c00, "Original MAIN placement differs")
    table = region(resident, load[1] + 0x1485e0 - load[2], 32, "Original method table")
    methods = (0x6a0060, 0x6a0050, 0x69ff60, 0x69ff50, 0x62e5a0, 0x69ff40)
    require(struct.unpack("<8I", table) == (0, 0, *methods), "Original complete method table differs")
    caller = region(main, 0x29c4bc - main_address, 16, "Original indirect call")
    require(struct.unpack("<4I", caller) == (0x8c990070, 0x8f390014, 0x0320f809, 0),
            "Original dispatch loads, JALR or delay slot differ")
    installs = ((0x69fa64, 0x69fa6c, 0x69fa74), (0x6a0084, 0x6a008c, 0x6a0094))
    for addresses in installs:
        words = tuple(struct.unpack("<I", region(image, a - SLOT_START, 4, "Original table installation"))[0]
                      for a in addresses)
        require(words == (0x3c020015, 0x244285e0, 0xae020070),
                "Original table pointer installation at object offset 0x70 differs")
    target = region(image, 0x69ff50 - SLOT_START, 8, "Original return method")
    require(target == struct.pack("<2I", 0x03e00008, 0), "Original return/delay slot differ")
    return {"methods": list(methods), "table_address": 0x1485e0, "target_pointer_address": 0x1485f4,
            "table_sha256": hashlib.sha256(table).hexdigest(), "caller_start": 0x29c4bc,
            "caller_sha256": hashlib.sha256(caller).hexdigest(), "main_load_address": main_address,
            "pointer_installs": [list(a) for a in installs], "target_sha256": hashlib.sha256(target).hexdigest(),
            "runtime_object_snapshot": "unavailable; provenance is verified from original static bytes"}


def recovery_seeds(catalog, proof):
    starts = {item["guest_start"]: item["name"].rsplit("_0x", 1)[0][5:]
              for item in catalog["owners"].values()}
    old = {address for address, _ in catalog["entries"]}
    for address in proof["methods"]:
        if address not in old:
            require(address not in starts, "Recovered owner conflicts with new original method")
            starts[address] = f"verified_table_{address:08x}"
    seeds = "".join(f"{a:08x} {name}\n" for a, name in sorted(starts.items())).encode()
    callables = "".join(f"{address:08x}\n" for address, _ in catalog["entries"]).encode()
    return seeds, callables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--game", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--disc-dir", type=Path, help="Original PAL resident/MAIN inputs for callback provenance")
    parser.add_argument("--seeds", type=Path, help="Fresh Ghidra seeds; requires --disc-dir and --callables")
    parser.add_argument("--callables", type=Path, help="Recovered original callable addresses for fresh analysis")
    args = parser.parse_args()
    for output in (args.out, args.seeds, args.callables):
        if output is not None:
            require(not output.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
                    "Keep actual private GAME recovery outputs outside the checkout")
    require((args.seeds is None) == (args.callables is None) and
            (args.seeds is None or args.disc_dir is not None), "Seed export needs --disc-dir, --seeds and --callables")
    report = recover(args.exe.read_bytes(), args.game.read_bytes())
    if args.disc_dir is not None:
        proof = callback_provenance((args.disc_dir / "SLES_541.71").read_bytes(),
                                    (args.disc_dir / "MAIN.BIN").read_bytes(), args.game.read_bytes())
        report["callback_provenance"] = proof
        if args.seeds is not None:
            seeds, callables = recovery_seeds(report, proof)
            write_new(args.seeds, seeds)
            write_new(args.callables, callables)
            report["fresh_seed_sha256"] = hashlib.sha256(seeds).hexdigest()
            report["recovered_callables_sha256"] = hashlib.sha256(callables).hexdigest()
    write_new(args.out, (json.dumps(report, separators=(",", ":")) + "\n").encode())
    print(json.dumps({key: value for key, value in report.items() if key not in ("entries", "owners")}))


if __name__ == "__main__":
    main()
