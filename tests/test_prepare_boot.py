from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_boot import dispatch_addresses, extend_table
from prepare_game import FormatError
from prepare_boot_supplement import subtract, supplement_ranges

FIXTURE = """extern const uint32_t g_ps2RecompiledFunctionTableBase = 0x100008u;
extern const uint32_t g_ps2RecompiledFunctionTableEnd = 0x5918a4u;
extern const uint32_t g_ps2RecompiledFunctionTableSlotCount = 1197607u;
PS2Runtime::RecompiledFunction g_ps2RecompiledFunctionTable[1197607u] = {};
void initialize() {
    g_ps2RecompiledFunctionTable[0] = first;
    g_ps2RecompiledFunctionTable[1197606] = last;
}
"""


class BootTableTests(unittest.TestCase):
    def test_shared_decoded_entries_preserve_only_validated_baseline_addresses(self):
        original = FIXTURE.replace("= first;", "= first; // 0x100008").replace(
            "= last;", "= last; // 0x5918a0")
        self.assertEqual(dispatch_addresses(original), {0x100008, 0x5918a0})
        for bad in (original.replace("// 0x100008", "// 0x10000c"),
                    original + "g_ps2RecompiledFunctionTable[0] = first; // 0x100008\n",
                    FIXTURE):
            with self.assertRaises(FormatError): dispatch_addresses(bad)

    def test_extension_keeps_original_mapping_and_null_overlay_slots(self):
        result = extend_table(FIXTURE)
        self.assertIn("TableEnd = 0x6ef500u", result)
        self.assertIn("TableSlotCount = 1555774u", result)
        self.assertIn("Table[1555774u] = {}", result)
        assignments = lambda text: re.findall(r"Table\[\d+\] = \w+;", text)
        self.assertEqual(assignments(result), assignments(FIXTURE))
        self.assertEqual(result.count("= first;"), 1)
        self.assertNotIn("overlay", result)

    def test_other_build_or_missing_storage_is_rejected(self):
        for bad in (FIXTURE.replace("0x100008u", "0x100000u"),
                    FIXTURE.replace("Table[1197607u] = {};", "Table[];"),
                    FIXTURE + FIXTURE):
            with self.subTest(text=bad[:40]), self.assertRaises(FormatError): extend_table(bad)

    def test_supplement_extracts_only_new_instruction_intervals(self):
        self.assertEqual(subtract([(4, 24)], [(8, 12), (16, 20)]), [(4, 8), (12, 16), (20, 24)])
        self.assertEqual(subtract([(8, 20)], [(4, 24)]), [])
        self.assertEqual(subtract([(4, 12), (16, 24)], [(4, 8), (8, 12), (16, 24)]), [])
        self.assertEqual(subtract([(4, 8)], [(12, 16)]), [(4, 8)])

    def test_identified_entry_inside_previously_decoded_bytes_is_preserved(self):
        # A vtable entry can split an old decoded chunk without adding bytes.
        # Instruction subtraction alone would silently omit the new function.
        updated, baseline = [(4, 16), (16, 28), (32, 40)], [(4, 28)]
        self.assertEqual(supplement_ranges(updated, baseline, [16, 16]), [(16, 28), (32, 40)])
        with self.assertRaises(FormatError): supplement_ranges(updated, baseline, [20])


if __name__ == "__main__": unittest.main()
