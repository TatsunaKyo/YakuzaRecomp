// SPDX-License-Identifier: GPL-3.0-or-later
// Identify original PAL MPEG picture dispatch entries reached after IPU input.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;
import java.util.LinkedHashSet;

public class SeedMpegPictureCases extends GhidraScript {
    public void run() throws Exception {
        long[] expected = {0x12d4c0L, 0x12d4d4L, 0x12d504L, 0x12d528L, 0x12d528L};
        if (getInt(toAddr(0x12d4b8L)) != 0x00800008)
            throw new IllegalStateException("Original MPEG dispatch instruction differs");
        LinkedHashSet<Long> entries = new LinkedHashSet<>();
        // Verify all five words before changing analysis metadata.
        for (int i = 0; i < expected.length; ++i) {
            if (Integer.toUnsignedLong(getInt(toAddr(0x139db0L + i*4L))) != expected[i])
                throw new IllegalStateException("Original MPEG picture table differs at slot " + i);
            Address target = toAddr(expected[i]);
            var block = currentProgram.getMemory().getBlock(target);
            if (block == null || !block.isExecute() ||
                    (getFunctionAt(target) == null && getFunctionContaining(target) != null))
                throw new IllegalStateException("MPEG picture entry conflicts with classified code");
            entries.add(expected[i]);
        }
        for (long target : entries) {
            Address entry = toAddr(target);
            if (getFunctionAt(entry) == null) {
                if (getFunctionContaining(entry) != null)
                    throw new IllegalStateException("MPEG picture entry conflicts with a newly classified range");
                clearListing(entry, entry.add(3));
                if (!disassemble(entry) || createFunction(entry, String.format("pal_mpeg_picture_%08x", target)) == null)
                    throw new IllegalStateException("Could not identify original MPEG picture entry");
            }
            currentProgram.getListing().setComment(entry, CodeUnit.PLATE_COMMENT,
                "PAL MPEG picture branch entry from verified table0x139db0; original instructions preserved.");
        }
        analyzeChanges(currentProgram);
        println("Verified original MPEG picture table: five slots, four branch entries");
    }
}
