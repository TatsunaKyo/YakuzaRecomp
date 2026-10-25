import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_vu0 import corrected, prepare_batch, FIXTURE_SHA256, OLD, NEW


class Vu0PreparationTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "tests/fixtures/vu-macro/raw_vsub.cpp").read_bytes().replace(b"\r\n", b"\n")

    def test_supported_copy_and_repeat_preserve_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.cpp"
            source.write_bytes(self.raw)
            output = root / "private"
            inputs = [(source, FIXTURE_SHA256, 1, 0)]
            proofs = prepare_batch(inputs, output)
            fixed = output / source.name
            self.assertEqual(source.read_bytes(), self.raw)
            self.assertNotIn(OLD.encode(), fixed.read_bytes())
            self.assertIn(NEW.encode(), fixed.read_bytes())
            self.assertFalse(proofs[0]["original_instruction_bytes_changed"])
            os.utime(fixed, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
            timestamp = fixed.stat().st_mtime_ns
            self.assertEqual(prepare_batch(inputs, output), proofs)
            self.assertEqual(fixed.stat().st_mtime_ns, timestamp)

    def test_changed_instruction_rejects(self):
        with self.assertRaises(ValueError):
            corrected(self.raw.replace(b"PS2_VSUB", b"PS2_VADD"), FIXTURE_SHA256)

    def test_windows_line_endings_normalize(self):
        self.assertEqual(corrected(self.raw.replace(b"\n", b"\r\n"), FIXTURE_SHA256),
                         corrected(self.raw, FIXTURE_SHA256))

    def test_late_input_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first.cpp", root / "second.cpp"
            first.write_bytes(self.raw)
            second.write_bytes(self.raw + b"// changed\n")
            output = root / "private"
            with self.assertRaises(ValueError):
                prepare_batch([(first, FIXTURE_SHA256, 1, 0), (second, FIXTURE_SHA256, 1, 0)], output)
            self.assertFalse(output.exists())
            self.assertEqual(first.read_bytes(), self.raw)
