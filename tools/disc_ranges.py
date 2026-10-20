#!/usr/bin/env python3
"""Collect small original archive ranges on Windows, or import them privately."""
import argparse
import hashlib
from pathlib import Path
import re
import struct
import zipfile

MAGIC = b"YKRANGE\x01"
HEADER = struct.Struct("<8sQQQQ")
ARCHIVES = ("OGRE.CVM", "OGRE2.CVM", "OGRE3.CVM", "OGRE4.CVM")
MAX_RANGE = 24 * 1024 * 1024
MAX_BUNDLE = 28 * 1024 * 1024
NAME = re.compile(r"(OGRE(?:[234])?\.CVM)\.([0-9a-f]{16})\.ykr\Z")


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


def collect(disc, output, ranges):
    ranges = ranges or [(name, 0, 65536) for name in ARCHIVES[:3]]
    if (any(a not in ARCHIVES or o < 0 or not 0 < n <= MAX_RANGE for a, o, n in ranges) or
            len(set((a, o) for a, o, _ in ranges)) != len(ranges) or sum(n + HEADER.size for _, _, n in ranges) > MAX_BUNDLE):
        raise ValueError("Duplicate excerpt or bundle exceeds 28 MiB; collect smaller separate bundles")
    entries = []
    for archive, offset, length in ranges:
        source = disc / archive
        size = source.stat().st_size
        if not 0 < size <= 0xffffffff or offset >= size or length > size - offset:
            raise ValueError(f"Range exceeds {archive}; keep the original PAL archives unchanged")
        with source.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(length)
        if len(data) != length or source.stat().st_size != size:
            raise ValueError(f"{archive} changed while collecting")
        name = f"{archive}.{offset:016x}.ykr"
        entries.append((name, HEADER.pack(MAGIC, size, offset, length, fnv(data)) + data))
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in entries:
            bundle.writestr(name, data)
    print(f"Created {output} ({output.stat().st_size} bytes)")
    print("SHA-256:", hashlib.sha256(output.read_bytes()).hexdigest())
    print("Private original game excerpts: upload only to your development session, never to the public repository.")


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
    print(f"Imported {len(pending)} original excerpts into {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("collect", help="Copy requested bytes from unchanged original archives")
    pack.add_argument("--disc-dir", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--range", type=parse_range, action="append", dest="ranges")
    unpack = sub.add_parser("import", help="Import a private collection for the native boot probe")
    unpack.add_argument("--disc-dir", type=Path, required=True)
    unpack.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "collect":
            collect(args.disc_dir, args.output, args.ranges)
        else:
            install(args.bundle, args.disc_dir)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Disc range collection failed: {error}\n")


if __name__ == "__main__":
    main()
