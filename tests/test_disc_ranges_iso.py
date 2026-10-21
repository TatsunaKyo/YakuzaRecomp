import gzip
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import disc_ranges as ranges


def both(value, width):
    return value.to_bytes(width, "little") + value.to_bytes(width, "big")


def record(name, block, size, flags=0):
    result = bytearray(33 + len(name) + (len(name) % 2 == 0))
    result[0] = len(result)
    result[2:10] = both(block, 4)
    result[10:18] = both(size, 4)
    result[25] = flags
    result[28:32] = both(1, 2)
    result[32] = len(name)
    result[33:33+len(name)] = name
    return result


def iso_image(files, root_after_files=False):
    """Synthetic ISO9660; no original game bytes."""
    result = bytearray(24 * ranges.SECTOR)
    locations = {}
    for name, data in files.items():
        locations[name] = len(result) // ranges.SECTOR
        result.extend(data)
        result.extend(bytes((-len(result)) % ranges.SECTOR))
    root = len(result) // ranges.SECTOR if root_after_files else 20
    if root_after_files:
        result.extend(bytes(ranges.SECTOR))
    directory = record(b"\x00", root, ranges.SECTOR, 2) + record(b"\x01", root, ranges.SECTOR, 2)
    record_offsets = {}
    for name, data in files.items():
        record_offsets[name] = root * ranges.SECTOR + len(directory)
        directory += record((name + ";1").encode("ascii"), locations[name], len(data))
    result[root*ranges.SECTOR:root*ranges.SECTOR+len(directory)] = directory
    primary = bytearray(ranges.SECTOR)
    primary[:7] = b"\x01CD001\x01"
    primary[80:88] = both(len(result) // ranges.SECTOR, 4)
    primary[128:132] = both(ranges.SECTOR, 2)
    primary[156:190] = record(b"\x00", root, ranges.SECTOR, 2)
    result[16*ranges.SECTOR:17*ranges.SECTOR] = primary
    result[17*ranges.SECTOR:17*ranges.SECTOR+7] = b"\xffCD001\x01"
    return bytes(result), record_offsets


def contents(path):
    with zipfile.ZipFile(path) as bundle:
        return {name: ranges.decode(name, bundle.read(name)) for name in bundle.namelist()}


class IsoDiscRangesTests(unittest.TestCase):
    def test_iso_and_gzip_match_extracted_files(self):
        files = {"OGRE.CVM": bytes(range(256)) * 32, "OGRE2.CVM": b"second" * 2000,
                 "OGRE3.CVM": b"third" * 1000}
        # Unsorted and overlapping requests exercise forward scanning and exact offsets.
        requests = [("OGRE3.CVM", 1024, 600), ("OGRE.CVM", 4096, 500),
                    ("OGRE.CVM", 4000, 400), ("OGRE2.CVM", 7000, 200)]
        for root_after_files in (False, True):
            with self.subTest(root_after_files=root_after_files), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "Yakuza 日本語 (Europe)"; root.mkdir()
                for name, data in files.items():
                    (root / name).write_bytes(data)
                iso, _ = iso_image(files, root_after_files)
                image = root / "Yakuza (Europe).iso"; image.write_bytes(iso)
                compressed = root / "Yakuza (Europe).iso.gz"; compressed.write_bytes(gzip.compress(iso))
                before = hashlib.sha256(compressed.read_bytes()).hexdigest()
                folder_zip = root / "folder.zip"
                ranges.collect(root, folder_zip, requests)
                for source in (image, compressed):
                    output = root / (source.name + ".zip")
                    ranges.collect_iso(source, output, requests)
                    self.assertEqual(contents(output), contents(folder_zip))
                self.assertEqual(hashlib.sha256(compressed.read_bytes()).hexdigest(), before)

    def test_default_boot_collection_verifies_index_before_output(self):
        index = b"synthetic-index" + bytes(201346 - len(b"synthetic-index"))
        files = {"OGRE.CVM": b"first" * 2000, "OGRE2.CVM": b"second" * 2000,
                 "OGRE3.CVM": b"third" * 2000, "OGREDIR.BIN": index}
        requests = [(name, 0, 2048) for name in ranges.ARCHIVES[:3]] + [("OGRE.CVM", 4096, 200)]
        with tempfile.TemporaryDirectory() as temp, patch.object(ranges, "BOOT_RANGES", requests), \
                patch.object(ranges, "PAL_INDEX_SHA256", hashlib.sha256(index).hexdigest()):
            root = Path(temp)
            image = root / "game.iso.gz"
            image.write_bytes(gzip.compress(iso_image(files)[0]))
            output = root / "good.zip"
            ranges.collect_iso(image, output, None)
            self.assertEqual(len(contents(output)), 4)
            files["OGREDIR.BIN"] = b"!" + index[1:]
            image.write_bytes(gzip.compress(iso_image(files)[0]))
            with self.assertRaisesRegex(ValueError, "supported PAL"):
                ranges.collect_iso(image, root / "bad.zip", None)
            self.assertFalse((root / "bad.zip").exists())

    def test_malformed_iso_metadata_is_rejected(self):
        original, records = iso_image({"OGRE.CVM": b"data" * 1024})
        entry = records["OGRE.CVM"]
        cases = []
        bad = bytearray(original); bad[16*ranges.SECTOR+1] = 0; cases.append(bad)
        bad = bytearray(original); bad[16*ranges.SECTOR+130] ^= 1; cases.append(bad)
        bad = bytearray(original); bad[entry+25] |= 0x80; cases.append(bad)
        bad = bytearray(original); bad[entry+2:entry+10] = both(0x100000, 4); cases.append(bad)
        bad = bytearray(original); bad[entry] = 1; cases.append(bad)
        for data in cases:
            with self.subTest(data=data[:8]):
                with self.assertRaises(ValueError):
                    ranges.IsoReader(io.BytesIO(data), False).root_files()
        missing, _ = iso_image({"OTHER.CVM": b"data"})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "missing.iso"; source.write_bytes(missing)
            with self.assertRaisesRegex(ValueError, "does not contain OGRE.CVM"):
                ranges.collect_iso(source, root / "out.zip", [("OGRE.CVM", 0, 1)])
            self.assertFalse((root / "out.zip").exists())

    def test_truncated_required_data_and_existing_outputs(self):
        original, _ = iso_image({"OGRE.CVM": bytes(range(256)) * 64})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, data in [("short.iso", original[:24*ranges.SECTOR+10]),
                               ("short.iso.gz", gzip.compress(original)[:50])]:
                source = root / name; source.write_bytes(data)
                with self.assertRaises((ValueError, EOFError, OSError)):
                    ranges.collect_iso(source, root / "out.zip", [("OGRE.CVM", 0, 2048)])
                self.assertFalse((root / "out.zip").exists())
            existing = root / "existing.zip"; existing.write_bytes(b"preserve")
            with self.assertRaises(FileExistsError):
                ranges.collect_iso(root / "not-opened.iso.gz", existing, [("OGRE.CVM", 0, 1)])
            self.assertEqual(existing.read_bytes(), b"preserve")

    def test_cli_accepts_compressed_iso_with_spaces(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Sony PS2 日本語"; root.mkdir()
            source = root / "Yakuza (Europe) (En,Fr,De,Es,It).iso.gz"
            source.write_bytes(gzip.compress(iso_image({"OGRE.CVM": b"abcdefgh" * 1024})[0]))
            output = root / "small boot data.zip"
            tool = Path(ranges.__file__).resolve()
            result = subprocess.run([sys.executable, str(tool), "collect", "--iso", str(source),
                                     "--output", str(output), "--range", "OGRE.CVM:2048:32"],
                                    capture_output=True, text=True, timeout=20,
                                    env={**os.environ, "PYTHONIOENCODING": "cp1252"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(next(iter(contents(output).values()))[3], b"abcdefgh" * 4)
            self.assertEqual({p.name for p in root.iterdir()}, {source.name, output.name})

    def test_archive_metadata_supports_files_larger_than_two_gib(self):
        value = record(b"OGRE2.CVM;1", 24, 0xa0000000)
        name, offset, size, _ = ranges.iso_record(value, 4 * 1024 ** 3)
        self.assertEqual((name, offset, size), (b"OGRE2.CVM;1", 24 * ranges.SECTOR, 0xa0000000))


if __name__ == "__main__":
    unittest.main()
