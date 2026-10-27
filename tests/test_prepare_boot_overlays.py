from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from overlay_image import SLOT_START, analysis_elf, parse_overlay, verify
from prepare_boot_overlays import prepare
from prepare_game import FormatError
from test_overlay_image import fixture


def translated_fixture(folder):
    folder.mkdir(parents=True)
    image = bytes(fixture())
    layout = parse_overlay(image)
    elf = analysis_elf(image, layout, 0)
    address = SLOT_START + 128
    (folder / "analysis.elf").write_bytes(elf)
    (folder / "layout.json").write_text(json.dumps({
        **asdict(layout), "file_size": len(image),
        "file_sha256": hashlib.sha256(image).hexdigest(),
        "analysis_sha256": hashlib.sha256(elf).hexdigest()}))
    (folder / "decoded.csv").write_text(
        f"Name,Start,End,Size\noriginal,{address:#x},{address + 8:#x},8\n")
    digest = hashlib.sha256()
    for offset in (128, 132):
        digest.update(struct.pack("<I", SLOT_START + offset))
        digest.update(image[offset:offset + 4])
    (folder / "coverage.json").write_text(json.dumps({
        "range_count": 1, "instruction_count": 2, "covered_bytes": 8,
        "address_and_instruction_sha256": digest.hexdigest()}))
    (folder / "seeds.txt").write_text(f"{address:x} constructor\n")
    verify(folder)
    generated = folder / "generated"
    generated.mkdir()
    (generated / "register_functions.cpp").write_text(
        f"extern const uint32_t g_ps2RecompiledFunctionTableBase = {address:#x}u;\n"
        f"extern const uint32_t g_ps2RecompiledFunctionTableEnd = {address + 8:#x}u;\n"
        "extern const uint32_t g_ps2RecompiledFunctionTableSlotCount = 2u;\n"
        f"g_ps2RecompiledFunctionTable[0] = original; // {address:#x}\n")
    (generated / "original.cpp").write_text("// Synthetic original return instruction\n")
    return folder


class BootOverlayPreparationTests(unittest.TestCase):
    def link_source(self, link, target):
        try:
            link.symlink_to(target)
        except OSError as error:
            if sys.platform == "win32" and getattr(error, "winerror", None) == 1314:
                self.skipTest("Windows account cannot create symbolic links")
            raise

    def test_reused_translation_retains_its_physical_source_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = translated_fixture(root / "game")
            current = folder / "generated/original.cpp"
            original = root / "previous/original.cpp"
            original.parent.mkdir()
            current.rename(original)
            self.link_source(current, original)
            before = original.read_bytes()
            prepare([folder], root / "bindings")
            cmake = (root / "bindings/boot_overlays.cmake").read_text()
            self.assertIn(original.as_posix(), cmake)
            self.assertNotIn(current.as_posix(), cmake)
            self.assertEqual(original.read_bytes(), before)

    def test_distinct_overlay_symbols_cannot_alias_one_physical_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = translated_fixture(root / "game")
            generated = folder / "generated"
            self.link_source(generated / "other.cpp", generated / "original.cpp")
            register = generated / "register_functions.cpp"
            with register.open("a") as output:
                output.write(f"g_ps2RecompiledFunctionTable[1] = other; // {SLOT_START + 132:#x}\n")
            with self.assertRaisesRegex(FormatError, "same translation source"):
                prepare([folder], root / "bindings")
            self.assertFalse((root / "bindings").exists())

    def test_sparse_binding_preserves_inputs_and_canonical_unicode_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "alias").mkdir()
            folder = translated_fixture(root / "alias" / ".." / "Game data à")
            before = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            report = prepare([folder], root / "bindings")
            self.assertEqual(report[0]["sources"], 1)
            source = (root / "bindings/register_boot_overlays.cpp").read_text(encoding="utf-8")
            self.assertIn(f"{{0x{SLOT_START + 128:x}u, original}}", source)
            self.assertIn('2u, "game.bin", 224u', source)
            cmake = (root / "bindings/boot_overlays.cmake").read_text(encoding="utf-8")
            self.assertIn("[==[" + (folder.resolve() / "generated/original.cpp").as_posix() + "]==]", cmake)
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_changed_original_image_or_verification_proof_is_rejected(self):
        for filename in ("analysis.elf", "verification.json"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                folder = translated_fixture(root / "game")
                path = folder / filename
                if filename.endswith("elf"):
                    data = bytearray(path.read_bytes()); data[0x180] ^= 1
                    path.write_bytes(data)
                else:
                    report = json.loads(path.read_text()); report["instructions"] += 1
                    path.write_text(json.dumps(report))
                with self.assertRaises(FormatError): prepare([folder], root / "bindings")
                self.assertFalse((root / "bindings").exists())

    def test_bad_registration_or_missing_translation_fails_before_output(self):
        for defect in ("slot", "duplicate", "unrecognized", "missing-source", "missing-constructor"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                folder = translated_fixture(root / "game")
                path = folder / "generated/register_functions.cpp"
                text = path.read_text()
                if defect == "slot": text = text.replace("Table[0]", "Table[1]")
                if defect == "duplicate": text += text.splitlines()[-1] + "\n"
                if defect == "unrecognized": text = text.replace("= original;", "= (original);")
                if defect == "missing-source": (folder / "generated/original.cpp").unlink()
                if defect == "missing-constructor":
                    text = text.replace("Table[0]", "Table[1]").replace(
                        f"// {SLOT_START + 128:#x}", f"// {SLOT_START + 132:#x}")
                path.write_text(text)
                with self.assertRaises(FormatError): prepare([folder], root / "bindings")
                self.assertFalse((root / "bindings").exists())

    def test_duplicate_module_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folders = [translated_fixture(root / name) for name in ("first", "second")]
            with self.assertRaises(FormatError): prepare(folders, root / "bindings")

    def test_host_without_private_overlays_has_empty_bindings(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            self.assertEqual(prepare([], output), [])
            self.assertIn("return {};", (output / "register_boot_overlays.cpp").read_text())
            self.assertEqual((output / "boot_overlays.cmake").read_text(), "set(YAKUZA_BOOT_OVERLAY_TARGETS)\n")


if __name__ == "__main__": unittest.main()
