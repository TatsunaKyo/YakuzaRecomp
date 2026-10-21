// SPDX-License-Identifier: GPL-3.0-or-later
// Classify callbacks from the original PAL CVM filesystem interface table.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;

public class SeedCvmCallbacks extends GhidraScript {
    public void run() throws Exception {
        long table = 0x44e680L;
        long[] expected = {
            0, 0x1f2ef0, 0x1f2ef8, 0, 0x1f2f10, 0x1f2f28, 0x1f2f40,
            0x1f2f80, 0x1f2f98, 0, 0x1f2fb0, 0x1f2fc8, 0x1f3018, 0,
            0x1f3030, 0x1f3048, 0x1f3070, 0x1f3088, 0x1f3090, 0, 0, 0, 0,
            0x1f30a8, 0x1f31c8
        };
        // Check the complete original table before changing analysis metadata.
        for (int i = 0; i < expected.length; ++i) {
            if (Integer.toUnsignedLong(getInt(toAddr(table + i * 4L))) != expected[i])
                throw new IllegalStateException("PAL CVM callback table differs at slot " + i);
            if (expected[i] == 0) continue;
            Address entry = toAddr(expected[i]);
            var block = currentProgram.getMemory().getBlock(entry);
            if (block == null || !block.isExecute())
                throw new IllegalStateException("CVM callback is outside executable memory");
            if (getFunctionAt(entry) == null && getFunctionContaining(entry) != null)
                throw new IllegalStateException("CVM callback conflicts with a classified function: " + entry);
        }
        for (long target : expected) {
            if (target == 0) continue;
            Address entry = toAddr(target);
            if (getFunctionAt(entry) == null) {
                clearListing(entry, entry.add(3));
                if (!disassemble(entry) || createFunction(entry, String.format("pal_cvm_callback_%08x", target)) == null)
                    throw new IllegalStateException("Could not classify original CVM callback: " + entry);
            }
            currentProgram.getListing().setComment(entry, CodeUnit.PLATE_COMMENT,
                "Original PAL CVM callback from verified table 0x44e680; instruction bytes preserved.");
        }
        analyzeChanges(currentProgram);
        println("Classified original PAL CVM filesystem callback table");
    }
}
