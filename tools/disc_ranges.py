#!/usr/bin/env python3
"""Collect small original archive ranges on Windows, or import them privately."""
import argparse
from contextlib import ExitStack
import gzip
import hashlib
from pathlib import Path
import re
import struct
import sys
import zipfile
import zlib

MAGIC = b"YKRANGE\x01"
HEADER = struct.Struct("<8sQQQQ")
ARCHIVES = ("OGRE.CVM", "OGRE2.CVM", "OGRE3.CVM", "OGRE4.CVM")
MAX_RANGE = 24 * 1024 * 1024
MAX_BUNDLE = 28 * 1024 * 1024
NAME = re.compile(r"(OGRE(?:[234])?\.CVM)\.([0-9a-f]{16})\.ykr\Z")
# Verified PAL index: /MEDIA/SE/00000_CMN.DAT, first observed missing asset.
PAL_INDEX_SHA256 = "71f0ae7b805d34262f6218178806284e92a5cf393bdf083e8e19d135d9940e99"
BOOT_RANGES = [(name, 0, 65536) for name in ARCHIVES[:3]] + [("OGRE.CVM", 106305536, 292864)]
SECTOR = 2048
MAX_ISO = 9 * 1024 ** 3


def fnv(data):
    value = 0xcbf29ce484222325
    for byte in data:
        value = ((value ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return value


def decode(name, blob):
    match = NAME.fullmatch(name)
    if not match or len(blob) <= HEADER.size or len(blob) > MAX_RANGE + HEADER.size:
        raise ValueError("Invalid archive excerpt name or size")
    magic, size, offset, length, digest = HEADER.unpack_from(blob)
    data = blob[HEADER.size:]
    if (magic != MAGIC or not 0 < size <= 0xffffffff or offset >= size or
            offset != int(match[2], 16) or length != len(data) or length > size - offset or fnv(data) != digest):
        raise ValueError("Invalid or corrupt archive excerpt")
    return match[1], size, offset, data


def parse_range(value):
    try:
        archive, offset, length = value.split(":")
        offset, length = int(offset, 0), int(length, 0)
        if archive not in ARCHIVES or offset < 0 or not 0 < length <= MAX_RANGE:
            raise ValueError()
        return archive, offset, length
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use OGRE.CVM:OFFSET:LENGTH, with decimal or 0x values; maximum 24 MiB") from error


def requested_ranges(ranges):
    ranges = ranges or BOOT_RANGES
    if (any(a not in ARCHIVES or o < 0 or not 0 < n <= MAX_RANGE for a, o, n in ranges) or
            len(set((a, o) for a, o, _ in ranges)) != len(ranges) or sum(n + HEADER.size for _, _, n in ranges) > MAX_BUNDLE):
        raise ValueError("Duplicate excerpt or bundle exceeds 28 MiB; collect smaller separate bundles")
    return ranges


def verify_boot_index(data):
    if len(data) != 201346 or hashlib.sha256(data).hexdigest() != PAL_INDEX_SHA256:
        raise ValueError("The default boot collection requires the supported PAL OGREDIR.BIN")


def display_path(path):
    # Redirected Windows consoles can use a legacy code page. Keep reporting
    # usable even when a valid source/output path contains other characters.
    encoding = sys.stdout.encoding or "utf-8"
    return str(path).encode(encoding, "backslashreplace").decode(encoding)


def write_bundle(output, entries):
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in entries:
            bundle.writestr(name, data)
    print(f"Created {display_path(output)} ({output.stat().st_size} bytes)")
    print("SHA-256:", hashlib.sha256(output.read_bytes()).hexdigest())
    print("Private original game excerpts: upload only to your development session, never to the public repository.")


def encoded_range(archive, size, offset, data):
    return f"{archive}.{offset:016x}.ykr", HEADER.pack(MAGIC, size, offset, len(data), fnv(data)) + data


def collect(disc, output, ranges):
    if output.exists():
        raise FileExistsError(f"Choose a new output filename; {output} already exists")
    requests = requested_ranges(ranges)
    if not ranges:
        index = disc / "OGREDIR.BIN"
        if index.stat().st_size != 201346:
            raise ValueError("The default boot collection requires the supported PAL OGREDIR.BIN")
        verify_boot_index(index.read_bytes())
    entries = []
    for archive, offset, length in requests:
        source = disc / archive
        size = source.stat().st_size
        if not 0 < size <= 0xffffffff or offset >= size or length > size - offset:
            raise ValueError(f"Range exceeds {archive}; keep the original PAL archives unchanged")
        with source.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(length)
        if len(data) != length or source.stat().st_size != size:
            raise ValueError(f"{archive} changed while collecting")
        entries.append(encoded_range(archive, size, offset, data))
    write_bundle(output, entries)


def both_endian(data, at, width):
    little = int.from_bytes(data[at:at+width], "little")
    big = int.from_bytes(data[at+width:at+2*width], "big")
    if little != big or at + 2 * width > len(data):
        raise ValueError("Inconsistent ISO9660 metadata")
    return little


def iso_record(record, volume_size):
    if len(record) < 34 or record[0] != len(record) or not 0 < record[32] <= len(record) - 33:
        raise ValueError("Invalid ISO9660 directory record")
    if record[1] or record[25] & 0x80 or record[26] or record[27]:
        raise ValueError("ISO extended attributes, interleaved files and multiple extents are unsupported")
    if both_endian(record, 28, 2) != 1:
        raise ValueError("Multiple ISO volumes are unsupported")
    offset = both_endian(record, 2, 4) * SECTOR
    size = both_endian(record, 10, 4)
    if offset > volume_size or size > volume_size - offset:
        raise ValueError("ISO9660 file extent exceeds the declared volume")
    return record[33:33+record[32]], offset, size, record[25]


class IsoReader:
    def __init__(self, stream, compressed):
        self.stream, self.compressed = stream, compressed

    def read(self, offset, length):
        if self.compressed:
            if offset < self.stream.tell():
                self.stream.seek(0)
            report_at = (self.stream.tell() // (512 * 1024 ** 2) + 1) * (512 * 1024 ** 2)
            while self.stream.tell() < offset:
                chunk = self.stream.read(min(1024 ** 2, offset - self.stream.tell()))
                if not chunk:
                    raise ValueError("Compressed ISO ends before a required file extent")
                if self.stream.tell() >= report_at:
                    print(f"Scanned {self.stream.tell() // (1024 ** 2)} MiB of compressed ISO...", flush=True)
                    report_at += 512 * 1024 ** 2
        else:
            self.stream.seek(offset)
        data = self.stream.read(length)
        if len(data) != length:
            raise ValueError("ISO ends before a required file extent")
        return data

    def root_files(self):
        primary = None
        for block in range(16, 80):
            descriptor = self.read(block * SECTOR, SECTOR)
            if descriptor[1:6] != b"CD001" or descriptor[6] != 1:
                raise ValueError("Expected an ISO9660 .iso with 2048-byte sectors")
            if descriptor[0] == 1:
                primary = descriptor
                break
            if descriptor[0] == 255:
                break
        if primary is None or both_endian(primary, 128, 2) != SECTOR:
            raise ValueError("Missing ISO9660 primary descriptor or unsupported sector size")
        volume_size = both_endian(primary, 80, 4) * SECTOR
        if not 17 * SECTOR <= volume_size <= MAX_ISO:
            raise ValueError("ISO volume size is outside the supported PS2 DVD bounds")
        name, offset, length, flags = iso_record(primary[156:156+primary[156]], volume_size)
        if name != b"\x00" or not flags & 2 or not 0 < length <= 1024 ** 2:
            raise ValueError("Invalid ISO9660 root directory")
        directory = self.read(offset, length)
        files, cursor = {}, 0
        while cursor < len(directory):
            count = directory[cursor]
            if count == 0:
                cursor = (cursor // SECTOR + 1) * SECTOR
                continue
            if count > len(directory) - cursor or count > SECTOR - cursor % SECTOR:
                raise ValueError("ISO directory record crosses a sector boundary")
            name, offset, size, flags = iso_record(directory[cursor:cursor+count], volume_size)
            cursor += count
            if name in (b"\x00", b"\x01") or flags & 2:
                continue
            try:
                name = name.decode("ascii").upper().split(";", 1)[0]
            except UnicodeDecodeError as error:
                raise ValueError("Unsupported ISO9660 filename encoding") from error
            if name in files:
                raise ValueError(f"Ambiguous ISO9660 root filename: {name}")
            files[name] = offset, size
        return files


def collect_iso(image, output, ranges):
    if output.exists():
        raise FileExistsError(f"Choose a new output filename; {output} already exists")
    requests = requested_ranges(ranges)
    with ExitStack() as stack:
        raw = stack.enter_context(image.open("rb"))
        compressed = raw.read(2) == b"\x1f\x8b"
        raw.seek(0)
        stream = stack.enter_context(gzip.GzipFile(fileobj=raw, mode="rb")) if compressed else raw
        reader = IsoReader(stream, compressed)
        print("Reading compressed ISO; scanning may take several minutes..." if compressed else "Reading ISO...", flush=True)
        files = reader.root_files()
        reads = []
        for archive, offset, length in requests:
            if archive not in files:
                raise ValueError(f"ISO root does not contain {archive}")
            base, size = files[archive]
            if not 0 < size <= 0xffffffff or offset >= size or length > size - offset:
                raise ValueError(f"Requested range exceeds {archive}")
            reads.append((base + offset, archive, size, offset, length))
        if not ranges:
            if "OGREDIR.BIN" not in files or files["OGREDIR.BIN"][1] != 201346:
                raise ValueError("The default boot collection requires the supported PAL OGREDIR.BIN")
            base, size = files["OGREDIR.BIN"]
            reads.append((base, "OGREDIR.BIN", size, 0, size))
        entries = []
        # Ascending disc offsets avoid repeated decompression for normal ISOs.
        for absolute, archive, size, offset, length in sorted(reads):
            print(f"Reading {archive}, byte {offset}, length {length}...", flush=True)
            data = reader.read(absolute, length)
            if archive == "OGREDIR.BIN":
                verify_boot_index(data)
            else:
                entries.append(encoded_range(archive, size, offset, data))
    write_bundle(output, entries)


def install(bundle, disc):
    target = disc / ".yakuza-disc-ranges"
    if target.is_symlink():
        raise ValueError("Excerpt directory must not be a symbolic link")
    pending = {}
    with zipfile.ZipFile(bundle) as source:
        entries = source.infolist()
        if not entries or len(entries) > 4096 or sum(e.file_size for e in entries) > MAX_BUNDLE:
            raise ValueError("Invalid or oversized excerpt bundle")
        for entry in entries:
            if entry.filename in pending or not NAME.fullmatch(entry.filename) or entry.file_size > MAX_RANGE + HEADER.size:
                raise ValueError("Invalid or duplicate excerpt entry")
            data = source.read(entry)
            archive, size, offset, payload = decode(entry.filename, data)
            # Verify all existing overlapping excerpts before creating any output.
            if target.exists():
                for old in target.glob(archive + ".*.ykr"):
                    if old.is_symlink() or old.stat().st_size > MAX_RANGE + HEADER.size:
                        raise ValueError("Invalid existing excerpt")
                    _, old_size, old_offset, old_payload = decode(old.name, old.read_bytes())
                    begin, end = max(offset, old_offset), min(offset + len(payload), old_offset + len(old_payload))
                    if size != old_size or (begin < end and payload[begin-offset:end-offset] != old_payload[begin-old_offset:end-old_offset]):
                        raise ValueError("Archive excerpts disagree; preserve the original PAL edition")
            for other_name, other in pending.items():
                other_archive, other_size, other_offset, other_payload = decode(other_name, other)
                begin, end = max(offset, other_offset), min(offset + len(payload), other_offset + len(other_payload))
                if archive == other_archive and (size != other_size or (begin < end and payload[begin-offset:end-offset] != other_payload[begin-other_offset:end-other_offset])):
                    raise ValueError("Archive excerpts disagree")
            existing = target / entry.filename
            if existing.exists() and (existing.is_symlink() or existing.read_bytes() != data):
                raise ValueError("Refusing to replace a different existing excerpt")
            pending[entry.filename] = data
    target.mkdir(parents=True, exist_ok=True)
    for name, data in pending.items():
        path = target / name
        if not path.exists():
            with path.open("xb") as output:
                output.write(data)
    print(f"Imported {len(pending)} original excerpts into {display_path(target)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("collect", help="Copy requested bytes from unchanged original archives")
    source = pack.add_mutually_exclusive_group(required=True)
    source.add_argument("--disc-dir", type=Path, help="Extracted PAL disc folder")
    source.add_argument("--iso", type=Path, help="PAL .iso or gzip-compressed .iso.gz; no full extraction needed")
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--range", type=parse_range, action="append", dest="ranges")
    unpack = sub.add_parser("import", help="Import a private collection for the native boot probe")
    unpack.add_argument("--disc-dir", type=Path, required=True)
    unpack.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "collect":
            if args.iso:
                collect_iso(args.iso, args.output, args.ranges)
            else:
                collect(args.disc_dir, args.output, args.ranges)
        else:
            install(args.bundle, args.disc_dir)
    except (OSError, EOFError, ValueError, zlib.error, zipfile.BadZipFile) as error:
        parser.exit(1, f"Disc range collection failed: {error}\n")


if __name__ == "__main__":
    main()
