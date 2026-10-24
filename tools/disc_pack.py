#!/usr/bin/env python3
"""Pack complete original archives into small split-ZIP volumes, or restore them privately."""
import argparse
from bisect import bisect_right
from contextlib import ExitStack
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
import zlib

import disc_ranges as ranges

LIMIT = 24 * 1024 ** 2
BLOCK = 1024 ** 2
FORMAT = "YakuzaOriginalArchives1"


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(BLOCK), b""):
            result.update(block)
    return result.hexdigest()


class SplitWriter(io.RawIOBase):
    """A non-seekable ZIP output; volume boundaries split compressed bytes."""
    def __init__(self, folder, limit):
        require(type(limit) is int and 0 < limit <= LIMIT, "Part size must be at most 24 MiB")
        self.folder, self.limit = folder, limit
        self.position = self.used = 0
        self.part = None
        self.parts = []
        self.hash = hashlib.sha256()

    def writable(self):
        return True

    def tell(self):
        return self.position

    def finish_part(self):
        if self.part is not None:
            name = Path(self.part.name).name
            self.part.close()
            self.parts.append({"name": name, "bytes": self.used, "sha256": self.part_hash.hexdigest()})
            self.part = None

    def write(self, data):
        if self.closed:
            raise ValueError("Output is closed")
        remaining = memoryview(data)
        while remaining:
            if self.part is None:
                self.part = (self.folder / f"originals.zip.{len(self.parts)+1:03d}").open("xb")
                self.used, self.part_hash = 0, hashlib.sha256()
            count = min(len(remaining), self.limit - self.used)
            block = remaining[:count]
            self.part.write(block)
            self.part_hash.update(block)
            self.hash.update(block)
            self.position += count
            self.used += count
            remaining = remaining[count:]
            if self.used == self.limit:
                self.finish_part()
        return len(data)

    def flush(self):
        if self.part is not None:
            self.part.flush()

    def close(self):
        self.finish_part()
        super().close()


def pack(source, output, archives, *, iso=False, part_bytes=LIMIT):
    archives = list(archives)
    require(archives and len(set(archives)) == len(archives) and
            all(name in ranges.ARCHIVES for name in archives), "Select distinct OGRE archive names")
    require(type(part_bytes) is int and 0 < part_bytes <= LIMIT, "Part size must be at most 24 MiB")
    if output.exists():
        raise FileExistsError("Choose a new output folder; existing files are never overwritten")
    with ExitStack() as stack:
        if iso:
            raw = stack.enter_context(source.open("rb"))
            compressed = raw.read(2) == b"\x1f\x8b"
            raw.seek(0)
            stream = stack.enter_context(gzip.GzipFile(fileobj=raw)) if compressed else raw
            reader = ranges.IsoReader(stream, compressed)
            roots = reader.root_files()
            require(all(name in roots for name in archives), "ISO is missing a selected archive")
            entries = sorted((roots[name][0], name, roots[name][1]) for name in archives)
        else:
            entries = [(0, name, (source / name).stat().st_size) for name in archives]
        require(all(0 < size <= 0xffffffff for _, _, size in entries) and
                sum(size for _, _, size in entries) <= ranges.MAX_ISO, "Invalid archive sizes")
        output.mkdir(parents=True)
        files = []
        with SplitWriter(output, part_bytes) as writer:
            with zipfile.ZipFile(writer, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=1, allowZip64=True) as bundle:
                for base, name, size in entries:
                    print(f"Packing {name}: {size:,} original bytes...", flush=True)
                    checksum = hashlib.sha256()
                    handle = None if iso else stack.enter_context((source / name).open("rb"))
                    with bundle.open(name, "w", force_zip64=True) as target:
                        for offset in range(0, size, BLOCK):
                            count = min(BLOCK, size - offset)
                            data = reader.read(base + offset, count) if iso else handle.read(count)
                            require(len(data) == count, "Original archive ends before its declared size")
                            checksum.update(data)
                            target.write(data)
                    files.append({"name": name, "bytes": size, "sha256": checksum.hexdigest()})
                bundle.writestr("originals.json", json.dumps({"format": FORMAT, "files": files}))
        manifest = {"format": FORMAT, "part_bytes": part_bytes, "zip_bytes": writer.position,
                    "zip_sha256": writer.hash.hexdigest(), "files": files, "parts": writer.parts}
        (output / "parts.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Created {len(manifest['parts'])} upload parts in {ranges.display_path(output)}")
    print("Supply every originals.zip.* part and parts.json privately; original data stays outside Git.")
    return manifest


class JoinedParts(io.RawIOBase):
    def __init__(self, paths, sizes):
        self.paths, self.starts = paths, [0]
        for size in sizes:
            self.starts.append(self.starts[-1] + size)
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        require(whence in (0, 1, 2), "Invalid seek mode")
        offset += self.position if whence == 1 else self.starts[-1] if whence == 2 else 0
        require(0 <= offset <= self.starts[-1], "ZIP seek exceeds supplied parts")
        self.position = offset
        return offset

    def read(self, count=-1):
        if count < 0:
            count = self.starts[-1] - self.position
        require(count <= 16 * BLOCK, "ZIP metadata read exceeds the supported bound")
        count = min(count, self.starts[-1] - self.position)
        data = bytearray()
        while count:
            index = bisect_right(self.starts, self.position) - 1
            amount = min(count, self.starts[index + 1] - self.position)
            with self.paths[index].open("rb") as source:
                source.seek(self.position - self.starts[index])
                block = source.read(amount)
            require(len(block) == amount, "Truncated ZIP part")
            data.extend(block)
            self.position += amount
            count -= amount
        return bytes(data)


def unpack(folder, disc):
    manifest_path = folder / "parts.json"
    require(not manifest_path.is_symlink() and manifest_path.stat().st_size <= BLOCK, "Invalid parts manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict) and manifest.get("format") == FORMAT, "Unsupported parts manifest")
    files, parts = manifest["files"], manifest["parts"]
    require(isinstance(files, list) and isinstance(parts, list) and
            0 < len(files) <= 4 and 0 < len(parts) <= 4096 and
            all(isinstance(item, dict) for item in files + parts), "Invalid file or part count")
    require(type(manifest["part_bytes"]) is int and 0 < manifest["part_bytes"] <= LIMIT, "Invalid part limit")
    names = [file["name"] for file in files]
    require(len(set(names)) == len(names) and all(name in ranges.ARCHIVES for name in names), "Invalid archive names")
    for file in files:
        require(type(file["bytes"]) is int and 0 < file["bytes"] <= 0xffffffff and
                re.fullmatch(r"[0-9a-f]{64}", file["sha256"]), "Invalid archive metadata")
    require(sum(file["bytes"] for file in files) <= ranges.MAX_ISO, "Archive set exceeds PS2 DVD bounds")
    total = sum(part["bytes"] for part in parts if type(part.get("bytes")) is int)
    require(total == manifest["zip_bytes"] and 0 < total <= ranges.MAX_ISO + 16 * BLOCK, "Invalid ZIP size")
    paths, sizes, checksum = [], [], hashlib.sha256()
    for index, part in enumerate(parts, 1):
        require(part["name"] == f"originals.zip.{index:03d}" and type(part["bytes"]) is int and
                0 < part["bytes"] <= manifest["part_bytes"], "Invalid ZIP part metadata")
        require(index == len(parts) or part["bytes"] == manifest["part_bytes"], "Incomplete middle ZIP part")
        path = folder / part["name"]
        require(not path.is_symlink() and path.stat().st_size == part["bytes"], "Missing or truncated ZIP part")
        current = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(BLOCK), b""):
                current.update(block)
                checksum.update(block)
        require(current.hexdigest() == part["sha256"], "ZIP part checksum mismatch")
        paths.append(path)
        sizes.append(part["bytes"])
    require(checksum.hexdigest() == manifest["zip_sha256"], "Complete ZIP checksum mismatch")
    disc.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        with JoinedParts(paths, sizes) as joined, zipfile.ZipFile(joined) as bundle:
            members = bundle.infolist()
            require(len(members) == len(files) + 1 and
                    {m.filename for m in members} == set(names) | {"originals.json"}, "Unexpected ZIP members")
            require(bundle.getinfo("originals.json").file_size <= BLOCK, "Oversized ZIP metadata")
            require(json.loads(bundle.read("originals.json")) == {"format": FORMAT, "files": files},
                    "ZIP and parts manifests disagree")
            for file in files:
                name, size = file["name"], file["bytes"]
                require(bundle.getinfo(name).file_size == size, "ZIP archive size mismatch")
                target = disc / name
                require(not target.is_symlink(), "Existing archive is a symlink")
                if target.exists():
                    require(target.stat().st_size == size and digest(target) == file["sha256"],
                            "Existing original archive differs; it will not be overwritten")
                with tempfile.NamedTemporaryFile(prefix=".incoming-", dir=disc, delete=False) as output:
                    temporary = Path(output.name)
                    staged.append((temporary, target))
                    current, copied = hashlib.sha256(), 0
                    with bundle.open(name) as source:
                        for block in iter(lambda: source.read(BLOCK), b""):
                            copied += len(block)
                            require(copied <= size, "Archive exceeds declared size")
                            current.update(block)
                            output.write(block)
                require(copied == size and current.hexdigest() == file["sha256"], "Original archive checksum mismatch")
                with temporary.open("rb") as complete:
                    for old in (disc / ".yakuza-disc-ranges").glob(name + ".*.ykr"):
                        require(not old.is_symlink() and old.stat().st_size <= ranges.MAX_RANGE + ranges.HEADER.size,
                                "Invalid existing excerpt")
                        archive, logical, offset, payload = ranges.decode(old.name, old.read_bytes())
                        require(archive == name and logical == size, "Existing excerpt belongs to another archive")
                        complete.seek(offset)
                        require(complete.read(len(payload)) == payload, "Complete archive differs from supplied excerpts")
        for temporary, target in staged:
            if target.exists():
                temporary.unlink()
            else:
                os.replace(temporary, target)
            print(f"Verified complete original archive: {target.name}")
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("pack", help="Create upload-sized split ZIP parts on Windows or Linux")
    source = create.add_mutually_exclusive_group(required=True)
    source.add_argument("--iso", type=Path)
    source.add_argument("--disc-dir", type=Path)
    create.add_argument("--archive", action="append", choices=ranges.ARCHIVES, required=True)
    create.add_argument("--output-dir", type=Path, required=True)
    restore = sub.add_parser("unpack", help="Verify all parts and restore full archives privately")
    restore.add_argument("--parts-dir", type=Path, required=True)
    restore.add_argument("--disc-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            pack(args.iso or args.disc_dir, args.output_dir, args.archive, iso=args.iso is not None)
        else:
            unpack(args.parts_dir, args.disc_dir)
    except (ValueError, KeyError, TypeError, OSError, EOFError, zipfile.BadZipFile, zlib.error) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
