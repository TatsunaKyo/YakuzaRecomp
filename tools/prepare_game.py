#!/usr/bin/env python3
"""Read-only PS2 Yakuza research tools; Python 3.10+, Windows or Linux.

The AVLZ algorithm and OGREDIR field layout were cross-checked against
LinuxJessi/YakuzaPythonExtractor (MIT). See THIRD_PARTY_NOTICES.md.
No game code or data is embedded in this source.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys

MAX_SMALL_FILE = 32 * 1024 * 1024
VOLUMES = [("OGREDIR.BIN", "OGRE.CVM"), ("OGREDIR2.BIN", "OGRE2.CVM"),
           ("OGREDIR3.BIN", "OGRE3.CVM"), ("OGREDIR4.BIN", "OGRE4.CVM")]
PAL_INPUTS = {
    "SYSTEM.CNF": "d81fe5b3efd1871448cae0073179e6da0571fb96bbb446a070950764eb872e55",
    "SLES_541.71": "fe2971fcedb85f329ceafb980b1335750d40510ef0768a1852a7fb0342d7b0c0",
    "MAIN.BIN": "4e1cef552e1fdbfda9bc795a7d81282ec8189d7ebe70ff4fe908b63316de28b2",
}


class FormatError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FormatError(message)


def region(blob: bytes, offset: int, size: int, label: str) -> bytes:
    require(0 <= offset <= len(blob) and 0 <= size <= len(blob) - offset,
            f"{label}: range outside file")
    return blob[offset:offset + size]


def read_small(path: Path) -> bytes:
    require(path.stat().st_size <= MAX_SMALL_FILE, f"{path.name}: expected a small metadata file")
    return path.read_bytes()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cstring(data: bytes, label: str) -> str:
    require(b"\0" in data, f"{label}: missing NUL terminator")
    try:
        return data.split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as error:
        raise FormatError(f"{label}: non-ASCII name") from error


def fixed_ascii(data: bytes, label: str) -> str:
    value = data.split(b"\0", 1)[0]
    require(all(32 <= byte <= 126 for byte in value), f"{label}: invalid ASCII name")
    return value.decode("ascii")


def safe_path(name: str, *, windows: bool = True) -> PurePosixPath:
    """Validate the disc's slash-separated names for Windows and POSIX."""
    require(name.startswith("/") and "\\" not in name, f"Invalid disc path: {name!r}")
    parts = name[1:].rstrip("/").split("/")
    require(all(parts), f"Empty component in disc path: {name!r}")
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved |= {f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)}
    for part in parts:
        require(part not in (".", "..") and not any(ord(c) < 32 for c in part),
                f"Unsafe disc path: {name!r}")
        if windows:
            require(part[-1:] not in (".", " ") and not any(c in '<>:"|?*' for c in part),
                    f"Windows-incompatible filename: {name!r}")
            require(part.split(".", 1)[0].upper() not in reserved, f"Windows device name: {name!r}")
    return PurePosixPath(*parts)


def avlz(blob: bytes, offset: int, expected_size: int) -> bytes:
    header = region(blob, offset, 12, "AVLZ header")
    magic, decoded, compressed = struct.unpack("<4sII", header)
    require(magic == b"AVLZ", "Missing AVLZ signature")
    require(decoded == expected_size and decoded <= MAX_SMALL_FILE, "Unexpected AVLZ decoded size")
    require(compressed >= 12, "Invalid AVLZ compressed size")
    source = region(blob, offset + 12, compressed - 12, "AVLZ stream")
    ring, output = bytearray(4096), bytearray()
    cursor, pos, flags, bits = 0xFEE, 0, 0, 0
    while len(output) < decoded:
        if bits == 0:
            require(pos < len(source), "Truncated AVLZ flags")
            flags, bits = source[pos], 8
            pos += 1
        literal = flags & 1
        flags >>= 1
        bits -= 1
        if literal:
            require(pos < len(source), "Truncated AVLZ literal")
            value = source[pos]
            pos += 1
            output.append(value)
            ring[cursor] = value
            cursor = (cursor + 1) & 4095
        else:
            require(pos + 2 <= len(source), "Truncated AVLZ back-reference")
            lo, hi = source[pos:pos + 2]
            pos += 2
            start, count = lo | ((hi & 0xF0) << 4), (hi & 15) + 3
            for i in range(count):
                if len(output) == decoded:
                    break
                value = ring[(start + i) & 4095]
                output.append(value)
                ring[cursor] = value
                cursor = (cursor + 1) & 4095
    return bytes(output)


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    lba: int
    size: int
    is_directory: bool

    @property
    def offset(self) -> int:
        return 0x1800 + self.lba * 2048


def ogredir(blob: bytes) -> list[ArchiveEntry]:
    region(blob, 0, 0x80, "OGREDIR header")
    count, _opaque_header_word = struct.unpack_from("<II", blob, 0x40)
    require(1 <= count <= 10000, "Invalid OGREDIR directory count")
    table_end = 0x80 + count * 64
    region(blob, 0x80, count * 64, "OGREDIR directory table")
    entries: list[ArchiveEntry] = []
    seen: set[str] = set()
    total_items = 0
    for i in range(count):
        record = region(blob, 0x80 + i * 64, 64, "Directory record")
        name = fixed_ascii(record[:56], "Directory name")
        require(name == "/" or name.endswith("/"), "Directory path must end with slash")
        if name != "/":
            safe_path(name, windows=False)
        nfiles, offset = struct.unpack_from("<II", record, 56)
        require(2 <= nfiles <= 100000, "Invalid directory entry count")
        total_items += nfiles
        require(total_items <= 250000, "OGREDIR exceeds the metadata budget")
        require(table_end <= offset <= len(blob) - 12, "Invalid directory block offset")
        raw_header = region(blob, offset, 12, "Directory AVLZ header")
        decoded = struct.unpack_from("<I", raw_header, 4)[0]
        require(20 + nfiles * 48 <= decoded <= 20 + nfiles * 48 + 127,
                "Directory block size does not match its entry count")
        block = avlz(blob, offset, decoded)
        first_count, second_count, _ = struct.unpack_from("<III", block)
        require(first_count == second_count == nfiles and block[12:20] == b"#DirLst#",
                "Invalid directory block header")
        for j in range(nfiles):
            item = region(block, 20 + j * 48, 48, "Directory item")
            _, size, _, lba = struct.unpack_from("<4I", item)
            flags = item[16]
            leaf = fixed_ascii(item[18:], "Entry name")
            if leaf in (".", ".."):
                continue
            require("/" not in leaf and bool(leaf), "Invalid directory leaf name")
            path = name + leaf
            safe_path(path, windows=False)
            key = path.casefold()
            require(key not in seen, f"Duplicate archive path: {path}")
            seen.add(key)
            entries.append(ArchiveEntry(path, lba, size, bool(flags & 2)))
    return entries


def elf_info(image: bytes) -> dict:
    require(len(image) >= 52 and image[:7] == b"\x7fELF\x01\x01\x01", "Expected little-endian ELF32 IRX")
    require(struct.unpack_from("<H", image, 18)[0] == 8, "IRX is not MIPS")
    shoff = struct.unpack_from("<I", image, 32)[0]
    shsize, shcount, names_index = struct.unpack_from("<3H", image, 46)
    require(shsize == 40 and 0 < shcount <= 4096 and names_index < shcount, "Invalid ELF section table")
    region(image, shoff, shcount * shsize, "ELF section headers")
    headers = [struct.unpack_from("<10I", image, shoff + i * 40) for i in range(shcount)]
    strings_header = headers[names_index]
    names = region(image, strings_header[4], strings_header[5], "ELF section names")
    module, version, imports = "", 0, []
    for header in headers:
        require(header[0] < len(names), "Invalid ELF section name offset")
        section_name = cstring(names[header[0]:], "ELF section name")
        if header[1] == 8:
            continue
        payload = region(image, header[4], header[5], "ELF section")
        if section_name == ".iopmod":
            require(len(payload) >= 27, "Short IOP module metadata")
            version = struct.unpack_from("<H", payload, 24)[0]
            module = cstring(payload[26:], "IOP module name").rstrip()
        if header[2] & 2:
            for start in range(0, max(0, len(payload) - 19), 4):
                if payload[start:start + 8] != b"\0\0\xe0A\0\0\0\0":
                    continue
                # Import names use all eight bytes for names like loadcore;
                # unlike ELF string tables, a full-width name needs no NUL.
                name_bytes = payload[start + 12:start + 20].split(b"\0", 1)[0]
                if not name_bytes or any(c < 33 or c > 126 for c in name_bytes):
                    continue
                library = name_bytes.decode("ascii")
                ordinals = []
                pos = start + 20
                while pos + 8 <= len(payload):
                    jump, ordinal = struct.unpack_from("<II", payload, pos)
                    if jump != 0x03E00008 or ordinal >> 16 != 0x2400:
                        break
                    ordinals.append(ordinal & 0xFFFF)
                    pos += 8
                imports.append({"library": library, "version": struct.unpack_from("<H", payload, start + 8)[0],
                                "ordinals": ordinals})
    require(bool(module), "Missing .iopmod module name")
    return {"module": module, "version": version, "entry": struct.unpack_from("<I", image, 24)[0], "imports": imports}


def irx_dat(blob: bytes) -> list[tuple[str, bytes, dict]]:
    region(blob, 0, 16, "IRX bundle header")
    groups = struct.unpack_from("<I", blob)[0]
    require(1 <= groups <= 16, "Invalid IRX group count")
    table_end = 16 + 16 * groups
    region(blob, 16, groups * 16, "IRX group table")
    output = []
    previous_group_end = table_end
    for group in range(groups):
        offset, size, _, tag = struct.unpack_from("<4I", blob, 16 + 16 * group)
        require(offset >= previous_group_end, "Overlapping IRX group")
        data = region(blob, offset, size, "IRX group")
        require(len(data) >= 16, "Short IRX group")
        count, group_tag = struct.unpack_from("<II", data)
        require(1 <= count <= 256 and group_tag == tag, "Invalid IRX group metadata")
        header_end = 16 + 16 * count
        region(data, 16, 16 * count, "IRX module table")
        previous_end = header_end
        for index in range(count):
            start, length, _, _ = struct.unpack_from("<4I", data, 16 + index * 16)
            require(start >= previous_end, "Overlapping IRX entries")
            image = region(data, start, length, "IRX image")
            if length:
                info = elf_info(image)
                leaf = re.sub(r"[^A-Za-z0-9_-]", "_", info["module"])
                output.append((f"{group:02d}-{index:02d}-{leaf}.irx", image, info))
            previous_end = start + length
        previous_group_end = offset + size
    return output


def romdir(blob: bytes) -> list[tuple[str, bytes]]:
    require(blob[:10].rstrip(b"\0") == b"RESET", "Expected RESET/ROMDIR image")
    region(blob, 0, 32, "ROMDIR header")
    require(blob[16:26].rstrip(b"\0") == b"ROMDIR", "Missing ROMDIR record")
    table_size = struct.unpack_from("<I", blob, 28)[0]
    require(32 <= table_size <= 16 * 1024 and table_size % 16 == 0, "Invalid ROMDIR size")
    region(blob, 0, table_size, "ROMDIR table")
    output, position, terminated = [], 0, False
    for offset in range(0, table_size, 16):
        record = blob[offset:offset + 16]
        if record[:10] == b"\0" * 10:
            terminated = True
            break
        name = cstring(record[:10], "ROMDIR name")
        require(re.fullmatch(r"[A-Z0-9_]+", name) is not None, "Invalid ROMDIR name")
        size = struct.unpack_from("<I", record, 12)[0]
        payload = region(blob, position, size, "ROMDIR file")
        if payload.startswith(b"\x7fELF"):
            elf_info(payload)
            output.append((name, payload))
        position += (size + 15) & ~15
    require(terminated, "ROMDIR terminator missing")
    return output


def write_new(path: Path, data: bytes) -> None:
    if path.exists():
        require(path.read_bytes() == data, f"Refusing to overwrite different file: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        target.write(data)


def inspect(disc: Path, output: Path) -> dict:
    report = {"target": "Windows x64", "serial": "SLES-54171", "inputs": {}, "modules": [], "archives": []}
    for name, expected in PAL_INPUTS.items():
        image = read_small(disc / name)
        require(sha256(image) == expected, f"{name}: differs from the supported PAL build")
        report["inputs"][name] = {"size": len(image), "sha256": expected}
    for name in ("IRX.DAT", "IOPRP300.IMG", *(pair[0] for pair in VOLUMES)):
        data = read_small(disc / name)
        report["inputs"][name] = {"size": len(data), "sha256": sha256(data)}
        if name == "IRX.DAT":
            for leaf, image, info in irx_dat(data):
                report["modules"].append({"source": name, "file": leaf, "size": len(image), "sha256": sha256(image), **info})
                write_new(output / "irx" / leaf, image)
        elif name == "IOPRP300.IMG":
            for leaf, image in romdir(data):
                report["modules"].append({"source": name, "file": leaf + ".irx", "size": len(image), "sha256": sha256(image), **elf_info(image)})
                write_new(output / "ioprp" / (leaf + ".irx"), image)
        else:
            cvm = dict(VOLUMES)[name]
            entries = ogredir(data)
            files = [{**asdict(e), "cvm_offset": e.offset} for e in entries if not e.is_directory]
            report["archives"].append({"index": name, "cvm": cvm, "file_count": len(files),
                "minimum_cvm_size": max(e.offset + e.size for e in entries), "files": files})
    encoded = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    write_new(output / "manifest.json", encoded)
    return report


def extract_overlays(disc: Path, output: Path) -> list[dict]:
    entries = [e for e in ogredir(read_small(disc / "OGREDIR4.BIN"))
               if not e.is_directory and e.path.startswith("/MEDIA4/MODULE/") and e.path.endswith(".BIN")]
    require(bool(entries), "No code overlays found")
    path = disc / "OGRE4.CVM"
    size = path.stat().st_size
    extracted = []
    # Validate all extents before writing any files. Reads are bounded to one module.
    with path.open("rb") as cvm:
        require(cvm.read(4) == b"CVMH", "Missing CVM signature")
        for entry in entries:
            require(entry.offset <= size and entry.size <= size - entry.offset, "CVM is truncated")
            require(64 <= entry.size <= MAX_SMALL_FILE, "Invalid overlay size")
        for entry in entries:
            cvm.seek(entry.offset)
            image = cvm.read(entry.size)
            require(len(image) == entry.size and image[:4] == b"MWo3", f"Invalid overlay: {entry.path}")
            destination = output.joinpath(*safe_path(entry.path).parts)
            require(destination.resolve().is_relative_to(output.resolve()), "Output path escapes extraction folder")
            write_new(destination, image)
            extracted.append({"path": entry.path, "size": entry.size, "sha256": sha256(image)})
    return extracted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "extract-overlays"))
    parser.add_argument("--disc-dir", required=True, type=Path, help="Folder of files extracted from your PAL disc")
    parser.add_argument("--out-dir", required=True, type=Path, help="Output folder outside the source checkout")
    args = parser.parse_args()
    require(not args.out_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
            "Choose an output folder outside the source checkout")
    if args.command == "inspect":
        report = inspect(args.disc_dir, args.out_dir)
        print(f"Indexed {sum(a['file_count'] for a in report['archives'])} files; extracted {len(report['modules'])} IOP images.")
        print("Manifest:", args.out_dir / "manifest.json")
    else:
        results = extract_overlays(args.disc_dir, args.out_dir)
        print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FormatError, OSError, struct.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
