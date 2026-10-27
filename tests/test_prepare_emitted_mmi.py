from pathlib import Path
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_emitted_mmi import corrected, prepare


class EmittedMmiPreparationTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "tests/fixtures/mmi/raw_permutations.cpp").read_bytes().replace(b"\r\n", b"\n")

    def test_supported_copy_preserves_original_and_repeat_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.cpp"
            source.write_bytes(self.raw)
            output = root / "private"
            staged = prepare([source], output)
            self.assertEqual(len(staged), 1)
            self.assertEqual(len(staged[0][4]), 4)
            self.assertEqual(source.read_bytes(), self.raw)
            fixed = staged[0][1]
            os.utime(fixed, ns=(1600000000000000000, 1600000000000000000))
            before = fixed.stat().st_mtime_ns
            prepare([source], output)
            self.assertEqual(fixed.stat().st_mtime_ns, before)

    def test_encoding_must_match_mnemonic(self):
        with self.assertRaises(ValueError):
            corrected(self.raw.replace(b"0x70084e89", b"0x70084e88"))

    def test_encoding_must_match_emitted_registers(self):
        with self.assertRaises(ValueError):
            corrected(self.raw.replace(b"0x70084e89", b"0x70084689"))

    def test_unknown_emitter_shape_rejected(self):
        with self.assertRaises(ValueError):
            corrected(self.raw.replace(b"_MM_SHUFFLE(2,3,0,1)", b"_MM_SHUFFLE(0,1,2,3)"))

    def test_complete_batch_validated_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first.cpp", root / "second.cpp"
            first.write_bytes(self.raw)
            second.write_bytes(self.raw.replace(b"0x70084e89", b"0x70084e88"))
            with self.assertRaises(ValueError):
                prepare([first, second], root / "private")
            self.assertFalse((root / "private").exists())

    def test_windows_line_endings_and_corrected_repeat(self):
        fixed, sites = corrected(self.raw)
        self.assertEqual(corrected(self.raw.replace(b"\n", b"\r\n")), (fixed, sites))
        self.assertEqual(corrected(fixed), (fixed, sites))

    def test_unrelated_code_preserved(self):
        data = b"// unrelated native code\nvoid native() {}\n"
        self.assertEqual(corrected(data), (data, []))


if __name__ == "__main__":
    unittest.main()
