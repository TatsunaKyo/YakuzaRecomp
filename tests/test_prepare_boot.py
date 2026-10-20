from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_boot import extend_table
from prepare_game import FormatError

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


if __name__ == "__main__": unittest.main()
