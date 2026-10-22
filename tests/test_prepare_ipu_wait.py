import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_ipu_wait import corrected, OLD, NEW


class IpuWaitPreparation(unittest.TestCase):
    def setUp(self):
        self.before = ("// Synthetic translated branch fixture\n" + OLD + "\n").encode()
        self.after = self.before.replace(OLD.encode(), NEW.encode())
        self.hashes = tuple(hashlib.sha256(s).hexdigest() for s in (self.before, self.after))

    def test_corrects_full_register_test_and_is_idempotent(self):
        self.assertEqual(corrected(self.before, *self.hashes), self.after)
        self.assertEqual(corrected(self.after, *self.hashes), self.after)
        self.assertEqual(corrected(self.before.replace(b"\n", b"\r\n"), *self.hashes), self.after)

    def test_rejects_other_native_changes(self):
        for data in (self.before + b" ", self.before.replace(b"17", b"18"),
                     self.after.replace(b">=", b">")):
            with self.assertRaises(ValueError):
                corrected(data, *self.hashes)


if __name__ == "__main__":
    unittest.main()
