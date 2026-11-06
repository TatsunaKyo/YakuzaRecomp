"""Original-free PE parser checks, not evidence of actual GAME coverage."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_game import FormatError
from prepare_boot_overlays import prepare
from recover_game_catalog import PE, recover
from recover_resident_catalog import restore_boot_extent


def pe_fixture():
    data = bytearray(0x400)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0x300, 3, 0xf0, 0)
    struct.pack_into("<H", data, 0x98, 0x20b)
    struct.pack_into("<Q", data, 0x98 + 24, 0x140000000)
    struct.pack_into("<8s6I2HI", data, 0x188, b".text", 0x200, 0x1000, 0x100, 0x200,
                     0, 0, 0, 0, 0x60000020)
    data[0x200:0x204] = b"test"
    struct.pack_into("<8sIhHBB", data, 0x300, b"local", 0, 1, 0, 3, 0)
    struct.pack_into("<8sIhHBB", data, 0x312, b"local", 4, 1, 0, 3, 0)
    struct.pack_into("<8sIhHBB", data, 0x324, struct.pack("<II", 0, 4), 8, 1, 0x20, 2, 0)
    name = b"long_function_name\0"
    struct.pack_into("<I", data, 0x336, 4 + len(name))
    data[0x33a:0x33a + len(name)] = name
    return data


class RecoveryParserTests(unittest.TestCase):
    def test_file_backed_executable_mapping(self):
        pe = PE(pe_fixture())
        self.assertEqual(pe.read(0x140001000, 4, 0x20000000), b"test")
        with self.assertRaises(FormatError): pe.read(0x140001000, 4, 0x80000000)

    def test_virtual_zero_fill_is_not_extracted_as_file_bytes(self):
        pe = PE(pe_fixture())
        for address, size in ((0x140000fff, 1), (0x140001100, 1), (0x1400010ff, 2)):
            with self.subTest(address=address, size=size), self.assertRaises(FormatError):
                pe.read(address, size)

    def test_local_symbol_names_can_repeat_at_different_addresses(self):
        symbols = PE(pe_fixture()).symbols()
        self.assertEqual(symbols["local"], {(0x140001000, 0), (0x140001004, 0)})
        self.assertEqual(symbols["long_function_name"], {(0x140001008, 0x20)})

    def test_invalid_headers_and_truncated_sections_are_rejected(self):
        for offset, value in ((0, 0), (0x84, 0), (0x98, 0), (0x188 + 20, 0xfffffff0)):
            with self.subTest(offset=offset):
                data = pe_fixture()
                struct.pack_into("<I", data, offset, value)
                with self.assertRaises(FormatError): PE(data)
        with self.assertRaises(FormatError): PE(bytes(12))

    def test_invalid_coff_string_and_auxiliary_extents_are_rejected(self):
        for defect in ("string", "auxiliary"):
            with self.subTest(defect=defect):
                data = pe_fixture()
                if defect == "string": struct.pack_into("<I", data, 0x328, 0xffffff00)
                else: data[0x335] = 255
                with self.assertRaises(FormatError): PE(data).symbols()

    def test_synthetic_pe_cannot_be_certified_as_the_actual_catalog(self):
        with self.assertRaisesRegex(FormatError, "verified private callback"):
            recover(bytes(pe_fixture()), b"not original GAME data")

    def test_actual_catalog_mode_requires_both_original_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "bindings"
            with self.assertRaisesRegex(FormatError, "both the original executable and GAME"):
                prepare([], output, recovered_executable=Path(temp) / "not-read.exe")
            self.assertFalse(output.exists())

    def test_main_extent_repair_keeps_neighbor_and_rejects_overlap(self):
        first = "Name,Start,End,Size\nFUN_0019f220,0x19f220,0x19f224,4\n"
        neighbor = "FUN_0019f2e0,0x19f2e0,0x19f2e4,4\n"
        self.assertEqual(restore_boot_extent(first + neighbor),
                         first.replace("0x19f224,4", "0x19f2e0,192") + neighbor)
        with self.assertRaisesRegex(FormatError, "overlapping"):
            restore_boot_extent(first + "other,0x19f2dc,0x19f2e0,4\n")


if __name__ == "__main__": unittest.main()
