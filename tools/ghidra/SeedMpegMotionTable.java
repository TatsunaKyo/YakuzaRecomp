// SPDX-License-Identifier: GPL-3.0-or-later
// Identify the remaining entries in the observed MPEG motion callback table.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import java.security.MessageDigest;

public class SeedMpegMotionTable extends GhidraScript {
    public void run() throws Exception {
        byte[] bytes = getBytes(toAddr(0x135e08), 64);
        StringBuilder digest = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(bytes))
            digest.append(String.format("%02x", value & 255));
        if (!digest.toString().equals("aa485420038da9378debe09e613ae774a01daca0c454c8d808bb33728c669716"))
            throw new IllegalStateException("Original MPEG motion table differs");
        long[] missing = {0x12b1f8, 0x12b2f0, 0x12b8b0, 0x12b9d0};
        for (long pc : missing) {
            Address entry = toAddr(pc);
            MemoryBlock block = currentProgram.getMemory().getBlock(entry);
            Function owner = getFunctionContaining(entry);
            if (block == null || !block.isExecute() || !block.isInitialized() || getInstructionAt(entry) == null)
                throw new IllegalStateException("MPEG motion entry is not decoded executable code");
            if (owner != null && !owner.getEntryPoint().equals(entry))
                throw new IllegalStateException("MPEG motion entry conflicts with a classified function");
        }
        int created = 0;
        for (long pc : missing) {
            Address entry = toAddr(pc);
            if (getFunctionAt(entry) == null) {
                if (createFunction(entry, String.format("mpeg_motion_%08x", pc)) == null)
                    throw new IllegalStateException("Cannot identify MPEG motion entry");
                ++created;
            }
        }
        analyzeChanges(currentProgram);
        println("Verified 16 MPEG motion pointers; newly identified entries: " + created);
    }
}
