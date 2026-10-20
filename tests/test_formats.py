from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_game import FormatError, avlz, elf_info, extract_overlays, irx_dat, ogredir, romdir, safe_path, write_new


def literal_avlz(data):
    encoded = b"".join(bytes([(1 << len(data[p:p + 8])) - 1]) + data[p:p + 8]
                       for p in range(0, len(data), 8))
    return b"AVLZ" + struct.pack("<II", len(data), len(encoded) + 12) + encoded


def index_fixture(name="GAME.BIN", size=64, lba=24):
    count = 3
    raw = bytearray(struct.pack("<III8s", count, count, 20, b"#DirLst#"))
    for leaf, flags, file_size, block in [(".", 2, 2048, 20), ("..", 2, 2048, 20), (name, 0, size, lba)]:
        raw += struct.pack("<4IBB30s", 0, file_size, 0, block, flags, 0, leaf.encode())
    raw += bytes((-len(raw)) % 64)
    blob = bytearray(0xC0)
    # The second header word is deliberately opaque, rather than a block bound.
    struct.pack_into("<II", blob, 0x40, 1, 0xFFFFFFFE)
    blob[0x80:0xB8] = b"/MEDIA4/MODULE/".ljust(56, b"\0")
    struct.pack_into("<II", blob, 0xB8, count, 0xC0)
    return bytes(blob) + literal_avlz(bytes(raw))


def irx_fixture():
    names = b"\0.shstrtab\0.iopmod\0"
    module = bytes(24) + struct.pack("<H", 0x0100) + b"testmod\0"
    payload = bytearray(52) + names + module
    module_offset = 52 + len(names)
    payload += bytes((-len(payload)) % 4)
    shoff = len(payload)
    payload += bytes(40)
    payload += struct.pack("<10I", 1, 3, 0, 0, 52, len(names), 0, 0, 1, 0)
    payload += struct.pack("<10I", 11, 1, 2, 0, module_offset, len(module), 0, 0, 4, 0)
    payload[:52] = struct.pack("<16sHHIIIIIHHHHHH", b"\x7fELF\x01\x01\x01" + bytes(9),
        0xFF80, 8, 1, 0x1234, 0, shoff, 0, 52, 0, 0, 40, 3, 1)
    return bytes(payload)


class AvlzTests(unittest.TestCase):
    def test_literals_and_ring_wrap(self):
        data = bytes(range(256)) * 33
        self.assertEqual(avlz(literal_avlz(data), 0, len(data)), data)

    def test_overlapping_back_reference(self):
        blob = b"AVLZ" + struct.pack("<II", 7, 16) + b"\x01A\xee\xf3"
        self.assertEqual(avlz(blob, 0, 7), b"AAAAAAA")

    def test_zero_initialized_dictionary(self):
        blob = b"AVLZ" + struct.pack("<II", 18, 15) + b"\0\0\x0f"
        self.assertEqual(avlz(blob, 0, 18), bytes(18))

    def test_truncated_streams(self):
        for stream in (b"\x01", b"\x00\xee"):
            blob = b"AVLZ" + struct.pack("<II", 3, 12 + len(stream)) + stream
            with self.subTest(stream=stream), self.assertRaises(FormatError): avlz(blob, 0, 3)

    def test_bounded_allocation(self):
        with self.assertRaises(FormatError): avlz(b"AVLZ" + struct.pack("<II", 0xFFFFFFFF, 12), 0, 0xFFFFFFFF)


class ArchiveTests(unittest.TestCase):
    def test_real_directory_shape(self):
        entries = ogredir(index_fixture())
        self.assertEqual([(e.path, e.size, e.offset) for e in entries], [("/MEDIA4/MODULE/GAME.BIN", 64, 0xD800)])

    def test_full_width_filename(self):
        name = "A" * 26 + ".BIN"
        self.assertEqual(ogredir(index_fixture(name))[0].path, "/MEDIA4/MODULE/" + name)

    def test_disc_names_can_differ_from_windows_names(self):
        self.assertTrue(ogredir(index_fixture("A."))[0].path.endswith("A."))
        with self.assertRaises(FormatError): safe_path("/MEDIA/A.")

    def test_escaping_paths_rejected(self):
        for name in ("/MEDIA/../outside", "/MEDIA/C:bad", "/MEDIA/NUL.BIN", "/MEDIA/COM1", "/MEDIA//file", "/MEDIA\\file"):
            with self.subTest(name=name), self.assertRaises(FormatError): safe_path(name)

    def test_corrupt_count_and_offset(self):
        for where, value in [(0x40, 0xFFFFFFFF), (0xBC, 0xFFFFFFF0)]:
            blob = bytearray(index_fixture()); struct.pack_into("<I", blob, where, value)
            with self.subTest(where=where), self.assertRaises(FormatError): ogredir(bytes(blob))

    def test_extracts_from_cvm_with_spaces_and_unicode_paths(self):
        with tempfile.TemporaryDirectory(prefix="Yakuza PAL ü ") as temp:
            root = Path(temp); disc = root / "disc files"; disc.mkdir()
            (disc / "OGREDIR4.BIN").write_bytes(index_fixture())
            cvm = bytearray(0xD800 + 64); cvm[:4] = b"CVMH"; cvm[0xD800:0xD804] = b"MWo3"
            (disc / "OGRE4.CVM").write_bytes(cvm)
            output = root / "extracted files"
            self.assertEqual(len(extract_overlays(disc, output)), 1)
            self.assertEqual((output / "MEDIA4/MODULE/GAME.BIN").read_bytes(), b"MWo3" + bytes(60))
            self.assertEqual(len(extract_overlays(disc, output)), 1)  # repeat without replacing originals

    def test_truncated_cvm_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            disc = Path(temp); (disc / "OGREDIR4.BIN").write_bytes(index_fixture())
            (disc / "OGRE4.CVM").write_bytes(b"CVMH")
            with self.assertRaises(FormatError): extract_overlays(disc, disc / "out")
            self.assertFalse((disc / "out").exists())

    def test_existing_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "keep.bin"; path.write_bytes(b"original")
            with self.assertRaises(FormatError): write_new(path, b"replacement")
            self.assertEqual(path.read_bytes(), b"original")


class ModuleTests(unittest.TestCase):
    def test_irx_metadata(self):
        info = elf_info(irx_fixture())
        self.assertEqual((info["module"], info["version"], info["entry"]), ("testmod", 0x0100, 0x1234))

    def test_irx_bundle(self):
        image = irx_fixture(); blob = bytearray(64)
        struct.pack_into("<I", blob, 0, 1)
        struct.pack_into("<4I", blob, 16, 32, 32 + len(image), 1, 0x44464C54)
        struct.pack_into("<4I", blob, 32, 1, 0x44464C54, 0, 0)
        struct.pack_into("<4I", blob, 48, 32, len(image), 0, 0)
        blob += image
        self.assertEqual(irx_dat(bytes(blob))[0][1], image)
        struct.pack_into("<I", blob, 48, 0)
        with self.assertRaises(FormatError): irx_dat(bytes(blob))

    def test_romdir_and_payload_bounds(self):
        image = irx_fixture(); blob = bytearray(64)
        struct.pack_into("<10sHI", blob, 0, b"RESET", 0, 0)
        struct.pack_into("<10sHI", blob, 16, b"ROMDIR", 0, 64)
        struct.pack_into("<10sHI", blob, 32, b"TESTMOD", 0, len(image))
        blob += image
        self.assertEqual(romdir(bytes(blob))[0], ("TESTMOD", image))
        with self.assertRaises(FormatError): romdir(bytes(blob[:-1]))

    def test_wrong_elf_machine_is_rejected(self):
        image = bytearray(irx_fixture()); struct.pack_into("<H", image, 18, 62)
        with self.assertRaises(FormatError): elf_info(bytes(image))


if __name__ == "__main__": unittest.main()
