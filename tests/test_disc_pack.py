import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import disc_pack
import disc_ranges
from test_disc_ranges_iso import iso_image


class DiscPackTests(unittest.TestCase):
    def files(self):
        random_bytes = random.Random(37)
        return {"OGRE.CVM": random_bytes.randbytes(70000), "OGRE3.CVM": random_bytes.randbytes(34001)}

    def prepare(self, root, files=None):
        files = self.files() if files is None else files
        source = root / "originals"; source.mkdir()
        for name, data in files.items():
            (source / name).write_bytes(data)
        output = root / "parts"
        manifest = disc_pack.pack(source, output, list(files), part_bytes=4096)
        return files, source, output, manifest

    def test_standard_zip_parts_and_full_archive_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files, _, parts, manifest = self.prepare(root)
            self.assertGreater(len(manifest["parts"]), 1)
            data = b"".join((parts / p["name"]).read_bytes() for p in manifest["parts"])
            self.assertTrue(all(p["bytes"] <= 4096 for p in manifest["parts"]))
            self.assertEqual(hashlib.sha256(data).hexdigest(), manifest["zip_sha256"])
            # Independently open concatenated volumes with the standard ZIP reader.
            with zipfile.ZipFile(io.BytesIO(data)) as bundle:
                for name, original in files.items():
                    self.assertEqual(bundle.read(name), original)
            restored = root / "restored"
            disc_pack.unpack(parts, restored)
            self.assertEqual({name: (restored / name).read_bytes() for name in files}, files)
            disc_pack.unpack(parts, restored)  # Existing identical originals stay valid.
            self.assertFalse(list(restored.glob(".incoming-*")))

    def test_compression_happens_before_volume_splitting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "originals"; source.mkdir()
            (source / "OGRE.CVM").write_bytes(bytes(2 * 1024 ** 2))
            manifest = disc_pack.pack(source, root / "parts", ["OGRE.CVM"], part_bytes=65536)
            self.assertEqual(len(manifest["parts"]), 1)
            self.assertLess(manifest["zip_bytes"], 65536)

    def test_zip64_offsets_above_four_gib_without_large_disk_allocation(self):
        class ZeroFile:
            def open(self, mode):
                class ZeroReader(io.BytesIO):
                    def read(self, count=-1):
                        amount = min(count, disc_pack.LIMIT - self.tell())
                        self.seek(self.tell() + amount)
                        return bytes(amount)
                return ZeroReader()

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prefix_parts = 171
            prefix_bytes = prefix_parts * disc_pack.LIMIT
            self.assertGreater(prefix_bytes, 2 ** 32)
            with disc_pack.SplitWriter(root, 4096) as writer:
                writer.position = prefix_bytes  # A virtual self-extracting prefix.
                with zipfile.ZipFile(writer, "w", allowZip64=True) as bundle:
                    with bundle.open("OGRE.CVM", "w", force_zip64=True) as target:
                        target.write(b"original-free ZIP64 boundary")
            paths = [ZeroFile()] * prefix_parts + [root / p["name"] for p in writer.parts]
            sizes = [disc_pack.LIMIT] * prefix_parts + [p["bytes"] for p in writer.parts]
            with disc_pack.JoinedParts(paths, sizes) as joined, zipfile.ZipFile(joined) as bundle:
                self.assertGreater(bundle.getinfo("OGRE.CVM").header_offset, 2 ** 32)
                self.assertEqual(bundle.read("OGRE.CVM"), b"original-free ZIP64 boundary")

    def test_iso_and_gzip_single_open_with_sorted_archive_extents(self):
        for compressed in (False, True):
            with self.subTest(compressed=compressed), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); files = self.files(); image, _ = iso_image(files)
                source = root / ("game.iso.gz" if compressed else "game.iso")
                source.write_bytes(gzip.compress(image) if compressed else image)
                before = source.read_bytes()
                with patch.object(disc_pack.gzip, "GzipFile", wraps=gzip.GzipFile) as opened:
                    manifest = disc_pack.pack(source, root / "parts", list(reversed(files)),
                                              iso=True, part_bytes=4096)
                    self.assertEqual(opened.call_count, 1 if compressed else 0)
                self.assertEqual([f["name"] for f in manifest["files"]], list(files))
                disc_pack.unpack(root / "parts", root / "restored")
                self.assertEqual({name: (root / "restored" / name).read_bytes() for name in files}, files)
                self.assertEqual(source.read_bytes(), before)

    def test_bad_parts_never_publish_an_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); files, _, parts, manifest = self.prepare(root)
            part = parts / manifest["parts"][1]["name"]; original = part.read_bytes()
            for mode in ("missing", "truncated", "changed"):
                with self.subTest(mode=mode):
                    if mode == "missing": part.unlink()
                    elif mode == "truncated": part.write_bytes(original[:-1])
                    else: part.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                    with self.assertRaises((ValueError, OSError)):
                        disc_pack.unpack(parts, root / "restored")
                    self.assertFalse(any((root / "restored" / name).exists() for name in files))
                    part.write_bytes(original)

    def test_conflicting_old_excerpts_abort_all_files_before_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); files, _, parts, _ = self.prepare(root)
            restored = root / "restored"; old = restored / ".yakuza-disc-ranges"; old.mkdir(parents=True)
            data = files["OGRE3.CVM"]
            name, encoded = disc_ranges.encoded_range("OGRE3.CVM", len(data), 32,
                                                      bytes(value ^ 1 for value in data[32:48]))
            (old / name).write_bytes(encoded)
            with self.assertRaisesRegex(ValueError, "differs from supplied excerpts"):
                disc_pack.unpack(parts, restored)
            self.assertTrue((old / name).exists())
            self.assertFalse(any((restored / name).exists() for name in files))
            self.assertFalse(list(restored.glob(".incoming-*")))
            name, encoded = disc_ranges.encoded_range("OGRE3.CVM", len(data), 32, data[32:48])
            (old / name).write_bytes(encoded)
            disc_pack.unpack(parts, restored)
            self.assertEqual((restored / "OGRE3.CVM").read_bytes(), data)

    def test_existing_files_and_output_folders_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); _, source, parts, _ = self.prepare(root)
            with self.assertRaises(FileExistsError):
                disc_pack.pack(source, parts, ["OGRE.CVM"])
            restored = root / "restored"; restored.mkdir()
            sentinel = restored / "OGRE.CVM"; sentinel.write_bytes(b"preserve original")
            with self.assertRaisesRegex(ValueError, "will not be overwritten"):
                disc_pack.unpack(parts, restored)
            self.assertEqual(sentinel.read_bytes(), b"preserve original")
            self.assertFalse((restored / "OGRE3.CVM").exists())

    def test_manifest_paths_and_oversized_parts_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); _, _, parts, manifest = self.prepare(root)
            for mutate in (lambda m: m["parts"][0].update(name="../outside"),
                           lambda m: m["files"][0].update(name="../OGRE.CVM"),
                           lambda m: m.update(part_bytes=disc_pack.LIMIT + 1)):
                changed = json.loads(json.dumps(manifest)); mutate(changed)
                (parts / "parts.json").write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    disc_pack.unpack(parts, root / "restored")
                self.assertFalse((root / "restored").exists())

    def test_cli_paths_with_spaces_and_unicode_on_legacy_console(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Sony PS2 日本語"; root.mkdir()
            source = root / "source files"; source.mkdir()
            (source / "OGRE.CVM").write_bytes(b"synthetic original" * 100)
            script = Path(disc_pack.__file__)
            env = dict(os.environ, PYTHONIOENCODING="cp1252")
            packed = subprocess.run([sys.executable, str(script), "pack", "--disc-dir", str(source),
                                     "--archive", "OGRE.CVM", "--output-dir", str(root / "upload parts")],
                                    env=env, capture_output=True)
            self.assertEqual(packed.returncode, 0, packed.stderr)
            restored = subprocess.run([sys.executable, str(script), "unpack", "--parts-dir", str(root / "upload parts"),
                                       "--disc-dir", str(root / "restored files")], env=env, capture_output=True)
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertEqual((root / "restored files/OGRE.CVM").read_bytes(), (source / "OGRE.CVM").read_bytes())


if __name__ == "__main__":
    unittest.main()
