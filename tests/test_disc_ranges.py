import tempfile
import unittest
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import disc_ranges as ranges


class DiscRangesTests(unittest.TestCase):
    def test_round_trip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "original"; original.mkdir()
            data = bytes(range(256)) * 1024
            (original / "OGRE.CVM").write_bytes(data)
            bundle = root / "boot-data.zip"
            ranges.collect(original, bundle, [("OGRE.CVM", 2048, 4096)])
            destination = root / "imported"
            ranges.install(bundle, destination)
            excerpt = next((destination / ".yakuza-disc-ranges").iterdir())
            archive, size, offset, payload = ranges.decode(excerpt.name, excerpt.read_bytes())
            self.assertEqual((archive, size, offset, payload), ("OGRE.CVM", len(data), 2048, data[2048:6144]))
            ranges.install(bundle, destination)
            with self.assertRaises(FileExistsError):
                ranges.collect(original, bundle, [("OGRE.CVM", 2048, 4096)])
            self.assertEqual((original / "OGRE.CVM").read_bytes(), data)

    def test_corruption_bounds_and_zip_paths(self):
        data = b"abcd"
        name = "OGRE.CVM.0000000000000000.ykr"
        blob = ranges.HEADER.pack(ranges.MAGIC, 4, 0, 4, ranges.fnv(data)) + data
        for bad_name, bad_blob in [("../" + name, blob), (name, blob[:-1]), (name, blob[:-1] + b"z"),
                                   (name, ranges.HEADER.pack(ranges.MAGIC, 3, 0, 4, ranges.fnv(data)) + data)]:
            with self.assertRaises(ValueError):
                ranges.decode(bad_name, bad_blob)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); bundle = root / "bad.zip"
            with zipfile.ZipFile(bundle, "w") as z:
                z.writestr(name, blob)
                z.writestr("../escape.ykr", blob)
            with self.assertRaises(ValueError):
                ranges.install(bundle, root / "disc")
            self.assertFalse((root / "disc").exists())

    def test_overlapping_originals_must_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); disc = root / "disc"; disc.mkdir()
            (disc / "OGRE.CVM").write_bytes(b"abcdefgh")
            one = root / "one.zip"; two = root / "two.zip"
            ranges.collect(disc, one, [("OGRE.CVM", 0, 4)])
            ranges.install(one, root / "target")
            (disc / "OGRE.CVM").write_bytes(b"abXYefgh")
            ranges.collect(disc, two, [("OGRE.CVM", 2, 4)])
            with self.assertRaises(ValueError):
                ranges.install(two, root / "target")


if __name__ == "__main__":
    unittest.main()
