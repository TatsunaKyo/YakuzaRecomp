#!/usr/bin/env python3
"""Create separate analysis images for Yakuza's mutually exclusive MWo3 overlays.

These are analysis inputs, not runnable PC executables. Original bytes are kept
unchanged. No copyrighted game bytes are embedded in this script.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from prepare_game import PAL_INPUTS, ogredir, read_small, region, require, sha256, write_new

SLOT_START = 0x62DC80
SLOT_END = 0x6EF500
PAL_CVM_SHA256 = "942c7e9cbf35e6ad5ff10aeaf76bb42c6d0f7852b3a2ea0d8630a2eb51e51373"


@dataclass(frozen=True)
class Overlay:
    name: str
    module_id: int
    address: int
    text_size: int
    mixed_size: int
    bss_size: int
    constructor_start: int
    constructor_end: int
    constructors: tuple[int, ...]

    @property
    def text_start(self): return self.address + 64

    @property
    def mixed_start(self): return self.text_start + self.text_size

    @property
    def bss_start(self): return self.mixed_start + self.mixed_size

    @property
    def memory_end(self): return self.bss_start + self.bss_size


def parse_overlay(image: bytes) -> Overlay:
    require(len(image) >= 64, "Truncated MWo3 header")
    magic, ident, address, text, mixed, bss, start, end = struct.unpack_from("<8I", image)
    require(magic == 0x336F574D, "Missing MWo3 signature")
    require(2 <= ident <= 12 and address == SLOT_START, "Not a PAL gameplay overlay")
    name_raw = image[32:64]
    require(b"\0" in name_raw, "Unterminated MWo3 name")
    name = name_raw.split(b"\0", 1)[0].decode("ascii")
    require(name.endswith(".bin") and name[:-4].replace("_", "").isalnum(), "Invalid MWo3 name")
    require(text > 0 and (text | mixed | bss) % 4 == 0, "Unaligned MWo3 regions")
    require(64 + text + mixed == len(image), "MWo3 payload sizes do not match the file")
    require(address + len(image) + bss <= SLOT_END, "Overlay exceeds the shared slot")
    require(address + 64 + text <= start <= end <= address + len(image), "Invalid constructor table extent")
    require((start | end) % 4 == 0, "Unaligned constructor table")
    ctors = struct.unpack_from(f"<{(end - start) // 4}I", image, start - address)
    require(all(p == 0 or address + 64 <= p < address + len(image) and p % 4 == 0 for p in ctors),
            "Constructor outside the initialized overlay")
    return Overlay(name, ident, address, text, mixed, bss, start, end, ctors)


def analysis_elf(image: bytes, overlay: Overlay, flags: int) -> bytes:
    """ELF32 R5900 view with one LOAD segment and distinct mixed/BSS regions."""
    # The first 64 bytes of the text region are alignment padding in all supplied
    # PAL modules. This seed is an analysis starting point, not a game entry ABI.
    entry = overlay.text_start
    while entry < overlay.mixed_start and image[entry - overlay.address:entry - overlay.address + 4] == bytes(4):
        entry += 4
    require(entry < overlay.mixed_start, "No nonzero code in the text region")
    blob = bytearray(0x100) + image
    sections = [("", 0, 0, 0, 0, 0, 0),
        (".overlay.header", 1, 3, overlay.address, 0x100, 64, 16),
        (".overlay.text", 1, 6, overlay.text_start, 0x140, overlay.text_size, 16),
        # Like MAIN, this region contains executable initialization functions.
        (".overlay.mixed", 1, 7, overlay.mixed_start, 0x140 + overlay.text_size, overlay.mixed_size, 16),
        (".overlay.bss", 8, 3, overlay.bss_start, len(blob), overlay.bss_size, 16)]
    names, offsets = bytearray(b"\0"), {"": 0}
    for name in [s[0] for s in sections[1:]] + [".shstrtab"]:
        offsets[name] = len(names)
        names += name.encode("ascii") + b"\0"
    names_offset = len(blob)
    blob += names
    sections.append((".shstrtab", 3, 0, 0, names_offset, len(names), 1))
    blob += bytes((-len(blob)) % 4)
    shoff = len(blob)
    for name, kind, attrs, addr, offset, size, align in sections:
        blob += struct.pack("<10I", offsets[name], kind, attrs, addr, offset, size, 0, 0, align, 0)
    blob[:52] = struct.pack("<16sHHIIIIIHHHHHH", b"\x7fELF\x01\x01\x01" + bytes(9),
        2, 8, 1, entry, 52, shoff, flags, 52, 32, 1, 40, len(sections), len(sections) - 1)
    blob[52:84] = struct.pack("<8I", 1, 0x100, overlay.address, overlay.address,
        len(image), len(image) + overlay.bss_size, 7, 16)
    require(blob[0x100:0x100 + len(image)] == image, "Analysis image changed original bytes")
    return bytes(blob)


def prepare(disc: Path, extracted: Path, output: Path) -> list[dict]:
    for name, expected in PAL_INPUTS.items():
        require(sha256(read_small(disc / name)) == expected, f"Unsupported PAL input: {name}")
    cvm = read_small(disc / "OGRE4.CVM")
    require(sha256(cvm) == PAL_CVM_SHA256, "Unsupported OGRE4.CVM build")
    index = read_small(disc / "OGREDIR4.BIN")
    require(sha256(index) == "093bbbfe7e8e62b613d245614315236042672714a031c8ea72bc894651682705", "Unsupported overlay index")
    extents = {Path(e.path).name: e for e in ogredir(index) if not e.is_directory}
    boot = read_small(disc / "SLES_541.71")
    flags = struct.unpack_from("<I", boot, 36)[0]
    images = sorted(extracted.glob("MEDIA4/MODULE/*.BIN"))
    require(len(images) == 11, "Expected all eleven extracted overlays")
    report, identifiers = [], set()
    for path in images:
        image = read_small(path)
        require(path.name in extents, "Overlay missing from original index")
        extent = extents[path.name]
        require(image == region(cvm, extent.offset, extent.size, "Original overlay"), "Extracted overlay differs from CVM")
        overlay = parse_overlay(image)
        require(overlay.name.upper() == path.name, "MWo3 filename mismatch")
        require(overlay.module_id not in identifiers, "Duplicate overlay ID")
        identifiers.add(overlay.module_id)
        # Check the original resident ELF's slot size for this module ID. The
        # header ID selects that program header, even though all addresses match.
        phoff = struct.unpack_from("<I", boot, 28)[0]
        phsize = struct.unpack_from("<H", boot, 42)[0]
        ph = struct.unpack("<8I", region(boot, phoff + overlay.module_id * phsize, 32, "Overlay slot"))
        require(ph[0] == 1 and ph[2] == overlay.address and ph[5] == len(image) + overlay.bss_size,
                "MWo3 memory extent differs from the original ELF slot")
        elf = analysis_elf(image, overlay, flags)
        folder = output / path.stem.lower()
        write_new(folder / "analysis.elf", elf)
        first = struct.unpack_from("<I", elf, 24)[0]
        seeds = [(first, "first_code")] + [(p, f"ctor_{i:02d}") for i, p in enumerate(overlay.constructors) if p]
        write_new(folder / "seeds.txt", "".join(f"{addr:08x} {name}\n" for addr, name in seeds).encode())
        item = {**asdict(overlay), "file_sha256": sha256(image), "analysis_sha256": sha256(elf),
                "analysis_seed": first, "file_size": len(image), "memory_end": overlay.memory_end}
        write_new(folder / "layout.json", (json.dumps(item, indent=2) + "\n").encode())
        report.append(item)
    write_new(output / "overlays.json", (json.dumps(report, indent=2) + "\n").encode())
    return report


def verify(folder: Path, *, write_outputs: bool = True) -> dict:
    elf = read_small(folder / "analysis.elf")
    layout = json.loads((folder / "layout.json").read_text())
    require(sha256(elf) == layout["analysis_sha256"], "Analysis ELF changed")
    with (folder / "decoded.csv").open() as source:
        rows = list(csv.DictReader(source))
    coverage = json.loads((folder / "coverage.json").read_text())
    require(bool(rows), "Empty decoded map")
    previous, count, digest = 0, 0, hashlib.sha256()
    for row in rows:
        lo, hi = int(row["Start"], 0), int(row["End"], 0)
        require(lo >= previous and lo >= layout["address"] + 64 and hi <= layout["address"] + layout["file_size"]
                and hi > lo and (lo | hi) % 4 == 0 and int(row["Size"]) == hi - lo, "Invalid decoded range")
        for address in range(lo, hi, 4):
            digest.update(struct.pack("<I", address))
            digest.update(elf[0x100 + address - layout["address"]:0x104 + address - layout["address"]])
            count += 1
        previous = hi
    require(count == coverage["instruction_count"] and len(rows) == coverage["range_count"]
            and count * 4 == coverage["covered_bytes"] and digest.hexdigest() == coverage["address_and_instruction_sha256"],
            "Ghidra decoded bytes differ from original overlay")
    seeds = [int(line.split()[0], 16) for line in (folder / "seeds.txt").read_text().splitlines()]
    require(all(any(int(row["Start"], 0) <= p < int(row["End"], 0) for row in rows) for p in seeds), "Missing analysis seed")
    config = {"input": str(folder / "analysis.elf"), "output": str(folder / "generated"),
              "ghidra_output": str(folder / "decoded.csv"), "single_file_output": False,
              "low_memory_mode": True, "output_worker_threads": 2,
              "patch_syscalls": False, "patch_cop0": False, "patch_cache": False, "stubs": [], "skip": []}
    # JSON strings are valid TOML strings; booleans are lower-case in both.
    text = "# Decoded overlay research probe, not a verified runnable game.\n[general]\n"
    text += "\n".join(f"{key} = {json.dumps(value)}" for key, value in config.items())
    text += "\n[patches]\ninstructions = []\n"
    if write_outputs:
        write_new(folder / "recompile.toml", text.encode())
    result = {"module": layout["name"], "ranges": len(rows), "instructions": count,
              "seed_count": len(seeds), "decoded_csv_sha256": sha256((folder / "decoded.csv").read_bytes())}
    if write_outputs:
        write_new(folder / "verification.json", (json.dumps(result, indent=2) + "\n").encode())
    else:
        require(json.loads((folder / "verification.json").read_text()) == result,
                "Overlay verification report differs from the current image/map")
    return result


def analyze(output: Path, ghidra: Path, recompiler: Path, selected: list[str]):
    require(ghidra.is_file() and recompiler.is_file(), "Ghidra or recompiler executable is missing")
    scripts = Path(__file__).resolve().parent / "ghidra"
    project = output / "ghidra-project"
    project.mkdir(parents=True, exist_ok=True)
    folders = [folder for folder in sorted(output.iterdir()) if (folder / "layout.json").is_file()]
    require(bool(folders) and set(selected) <= {folder.name for folder in folders}, "No prepared overlays or unknown --module")
    for folder in folders:
        if selected and folder.name not in selected: continue
        layout = json.loads((folder / "layout.json").read_text())
        print("Analyzing", layout["name"], flush=True)
        # Preserve projects and logs. A new output directory is required for a
        # changed analysis, avoiding stale success reports or silent overwrites.
        with (folder / "ghidra.log").open("x") as log:
            subprocess.run([str(ghidra), str(project), folder.name, "-import", str(folder / "analysis.elf"),
                "-processor", "r5900:LE:32:default", "-cspec", "default", "-max-cpu", "2",
                "-analysisTimeoutPerFile", "240", "-scriptPath", str(scripts),
                "-preScript", "SeedOverlay.java", str(folder / "seeds.txt"), folder.name,
                "-postScript", "ExportOverlay.java", str(folder / "decoded.csv"), str(folder / "coverage.json"),
                str(layout["address"] + 64), str(layout["address"] + layout["file_size"]), folder.name],
                check=True, stdout=log, stderr=subprocess.STDOUT)
        messages = (folder / "ghidra.log").read_text(errors="replace")
        require("Analysis succeeded for file:" in messages and "Import succeeded" in messages and
                "ERROR" not in messages and "analysis timed out" not in messages.lower(),
                "Ghidra reported an error; inspect ghidra.log")
        result = verify(folder)
        with (folder / "recompiler.log").open("x") as log:
            subprocess.run([str(recompiler), str(folder / "recompile.toml")], check=True, stdout=log, stderr=subprocess.STDOUT)
        messages = (folder / "recompiler.log").read_text()
        require("decode failures: 0" in messages and "Unhandled instructions: 0" in messages and
                "errors: 0" in messages and "Recompilation completed successfully" in messages,
                "Recompiler reported failures; inspect recompiler.log")
        print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "analyze", "verify"))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--disc-dir", type=Path)
    parser.add_argument("--extracted-dir", type=Path)
    parser.add_argument("--ghidra", type=Path)
    parser.add_argument("--recompiler", type=Path)
    parser.add_argument("--module", action="append", default=[])
    args = parser.parse_args()
    output = args.out_dir.resolve()
    require(not output.is_relative_to(Path(__file__).resolve().parents[1]), "Keep analysis outputs outside the source checkout")
    if args.command == "prepare":
        require(args.disc_dir is not None and args.extracted_dir is not None, "Need --disc-dir and --extracted-dir")
        print(json.dumps(prepare(args.disc_dir, args.extracted_dir, output), indent=2))
    elif args.command == "analyze":
        require(args.ghidra is not None and args.recompiler is not None, "Need --ghidra and --recompiler")
        analyze(output, args.ghidra, args.recompiler, args.module)
    else:
        print(json.dumps(verify(output), indent=2))


if __name__ == "__main__": main()
