from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from overlay_image import SLOT_START, analysis_elf, parse_overlay
from prepare_game import FormatError


def fixture():
    image = bytearray(64 + 128 + 32)
    struct.pack_into("<8I", image, 0, 0x336F574D, 2, SLOT_START, 128, 32, 64,
                     SLOT_START + 192, SLOT_START + 196)
    image[32:41] = b"game.bin\0"
    struct.pack_into("<2I", image, 128, 0x03E00008, 0)  # first real code after padding
    struct.pack_into("<I", image, 192, SLOT_START + 128)
    return image


class OverlayTests(unittest.TestCase):
    def test_layout_and_constructor(self):
        overlay = parse_overlay(fixture())
        self.assertEqual(overlay.constructors, (SLOT_START + 128,))
        self.assertEqual(overlay.bss_start, SLOT_START + 224)

    def test_payload_and_bss_overflow(self):
        for offset, value in [(12, 0xFFFFFFFC), (20, 0xFFFFFFFC), (8, 0), (4, 13)]:
            data = fixture(); struct.pack_into("<I", data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError): parse_overlay(data)

    def test_constructor_extent_and_targets(self):
        for offset, value in [(24, SLOT_START), (28, 0xFFFFFFFF), (192, SLOT_START + 224), (192, SLOT_START + 129)]:
            data = fixture(); struct.pack_into("<I", data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(FormatError): parse_overlay(data)

    def test_no_constructors(self):
        data = fixture(); struct.pack_into("<I", data, 28, SLOT_START + 192)
        self.assertEqual(parse_overlay(data).constructors, ())

    def test_analysis_preserves_bytes_and_zero_fill_extent(self):
        data = bytes(fixture()); overlay = parse_overlay(data)
        elf = analysis_elf(data, overlay, 0x20924000)
        self.assertEqual(elf[0x100:0x100 + len(data)], data)
        ph = struct.unpack_from("<8I", elf, 52)
        self.assertEqual(ph[2:6], (SLOT_START, SLOT_START, len(data), len(data) + 64))
        self.assertEqual(struct.unpack_from("<I", elf, 24)[0], SLOT_START + 128)

    def test_missing_code_and_truncation(self):
        data = fixture(); data[128:136] = bytes(8)
        with self.assertRaises(FormatError): analysis_elf(bytes(data), parse_overlay(data), 0)
        with self.assertRaises(FormatError): parse_overlay(fixture()[:-1])


if __name__ == "__main__": unittest.main()
