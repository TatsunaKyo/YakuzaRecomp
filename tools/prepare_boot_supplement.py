#!/usr/bin/env python3
"""Verify an updated decoded map and translate new code or newly identified entries."""
import argparse
import bisect
import csv
import hashlib
import io
import json
from pathlib import Path
import struct

from prepare_game import read_small, region, require, sha256, write_new


def read_ranges(path):
    rows = list(csv.DictReader(io.StringIO(read_small(path).decode())))
    result, previous = [], 0
    for row in rows:
        lo, hi = int(row["Start"], 0), int(row["End"], 0)
        require(lo >= previous and hi > lo and (lo | hi) % 4 == 0 and int(row["Size"]) == hi - lo,
                "Unaligned, overlapping or invalid decoded range")
        result.append((lo, hi))
        previous = hi
    require(bool(result) and len(result) <= 250000, "Invalid range count")
    return result


def subtract(ranges, covered):
    starts = [lo for lo, _ in covered]
    result = []
    for lo, hi in ranges:
        cursor, index = lo, max(0, bisect.bisect_right(starts, lo) - 1)
        while index < len(covered) and covered[index][0] < hi:
            first, last = covered[index]
            if cursor < first: result.append((cursor, min(first, hi)))
            cursor = max(cursor, last)
            index += 1
        if cursor < hi: result.append((cursor, hi))
    return result


def supplement_ranges(ranges, covered, entries):
    extra = subtract(ranges, covered)
    for entry in entries:
        matches = [(lo, hi) for lo, hi in ranges if lo == entry]
        require(len(matches) == 1, "Requested entry is not a distinct updated function range")
        extra.extend(subtract(matches, extra))
        extra.sort()
    return extra


def previous_entries(directory, current_ranges):
    report = json.loads(read_small(directory / "supplement-verification.json").decode())
    require(isinstance(report, dict), "Invalid previous supplemental verification report")
    entries = report.get("identified_entries", [])
    require(isinstance(entries, list) and len(entries) <= 250000 and
            all(type(entry) is int and 0x100008 <= entry < 0x592080 and entry % 4 == 0 for entry in entries),
            "Invalid previous supplemental entry list")
    require(not subtract(read_ranges(directory / "additional.csv"), current_ranges),
            "Updated analysis removed previously supplemental code; reassess first")
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--analysis-dir", required=True, type=Path)
    parser.add_argument("--entry", action="append", type=lambda value: int(value, 0), default=[],
                        help="Newly identified function start already present as decoded bytes")
    parser.add_argument("--previous-supplement", action="append", type=Path, default=[],
                        help="Retain identified entries and verify code coverage from an earlier supplement")
    args = parser.parse_args()
    root = args.analysis_dir.resolve()
    require(not root.is_relative_to(Path(__file__).resolve().parents[1]), "Keep generated code outside the checkout")
    image = read_small(root / "yakuza-pal-analysis.elf")
    require(sha256(image) == "c359e46e9a505e4df8f4e591bd036799db1984dbd06e2b143d8b0962af052689",
            "Analysis image differs from the verified PAL resident/MAIN image")
    shoff = struct.unpack_from("<I", image, 32)[0]
    shsize, count = struct.unpack_from("<HH", image, 46)
    require(shsize == 40, "Invalid ELF section record size")
    sections = []
    for i in range(count):
        header = struct.unpack("<10I", region(image, shoff + i * shsize, shsize, "ELF section"))
        if header[2] & 4 and header[1] != 8:
            sections.append((header[3], region(image, header[4], header[5], "Executable bytes")))
    old, new = read_ranges(args.baseline), read_ranges(root / "decoded-functions.csv")
    require(not subtract(old, new), "Updated analysis removed previously decoded code; reassess first")
    digest, instructions = hashlib.sha256(), 0
    for lo, hi in new:
        payload = [data[lo - address:hi - address] for address, data in sections
                   if address <= lo and hi <= address + len(data)]
        require(len(payload) == 1, "Decoded range is not uniquely in executable bytes")
        for address in range(lo, hi, 4):
            digest.update(struct.pack("<I", address))
            digest.update(payload[0][address - lo:address - lo + 4])
            instructions += 1
    coverage = json.loads((root / "decoded-coverage.json").read_text())
    require(coverage["range_count"] == len(new) and coverage["instruction_count"] == instructions and
            coverage["covered_bytes"] == instructions * 4 and
            coverage["address_and_instruction_sha256"] == digest.hexdigest(), "Decoded instruction digest mismatch")
    entries = list(args.entry)
    for previous in args.previous_supplement:
        entries.extend(previous_entries(previous, new))
    entries = list(dict.fromkeys(entries))
    extra = supplement_ranges(new, old, entries)
    require(bool(extra), "No new instructions to compile")
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("Name", "Start", "End", "Size"))
    for lo, hi in extra: writer.writerow((f"boot_supplement_{lo:08x}", hex(lo), hex(hi), hi - lo))
    write_new(root / "additional.csv", output.getvalue().encode())
    # Upstream registration requires the ELF entry to exist in this map. Change
    # only that synthetic header field; preserve every original loaded byte.
    supplemental_image = bytearray(image)
    struct.pack_into("<I", supplemental_image, 24, extra[0][0])
    write_new(root / "additional-input.elf", bytes(supplemental_image))
    config = {"input": str(root / "additional-input.elf"), "output": str(root / "generated"),
              "ghidra_output": str(root / "additional.csv"), "single_file_output": False,
              "low_memory_mode": True, "output_worker_threads": 2, "patch_syscalls": False,
              "patch_cop0": False, "patch_cache": False, "stubs": [], "skip": []}
    text = "[general]\n" + "\n".join(f"{k} = {json.dumps(v)}" for k, v in config.items())
    write_new(root / "additional.toml", (text + "\n[patches]\ninstructions = []\n").encode())
    report = {"new_ranges": len(extra), "new_instructions": sum((hi - lo) // 4 for lo, hi in extra),
              "verified_full_map_instructions": instructions, "identified_entries": entries,
              "previous_supplements": [str(path.resolve()) for path in args.previous_supplement]}
    write_new(root / "supplement-verification.json", (json.dumps(report, indent=2) + "\n").encode())
    print(json.dumps(report))


if __name__ == "__main__": main()
