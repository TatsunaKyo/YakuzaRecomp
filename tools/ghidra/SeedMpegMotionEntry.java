// SPDX-License-Identifier: GPL-3.0-or-later
// Recover the complete motion callback observed at 0x00129164.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import java.security.MessageDigest;

public class SeedMpegMotionEntry extends GhidraScript {
    public void run() throws Exception {
        Address first = toAddr(0x12ae70), last = toAddr(0x12af03);
        MemoryBlock block = currentProgram.getMemory().getBlock(first);
        if (block == null || !block.isExecute() || !block.isInitialized() || !block.contains(last))
            throw new IllegalStateException("MPEG callback is outside executable input");
        byte[] bytes = getBytes(first, 148);
        StringBuilder digest = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(bytes))
            digest.append(String.format("%02x", value & 255));
        if (!digest.toString().equals("d65d2bc711565d562d2222dc226d6505cad336af64958729582e787da4ca6c0c"))
            throw new IllegalStateException("Original MPEG motion callback differs");
        for (long pc=0x12ae70; pc<0x12af04; pc+=4) {
            Function owner = getFunctionContaining(toAddr(pc));
            if (owner != null && !owner.getEntryPoint().equals(first))
                throw new IllegalStateException("MPEG callback conflicts with another function");
        }
        boolean complete = true;
        for (long pc=0x12ae70; pc<0x12af04; pc+=4)
            complete &= getInstructionAt(toAddr(pc)) != null;
        Function function = getFunctionAt(first);
        if (complete && function != null && function.getBody().equals(new AddressSet(first, last))) {
            println("Verified complete MPEG motion callback; no changes");
            return;
        }
        // Typed data stopped automatic disassembly after the first LW. The
        // complete byte digest and conflict checks above precede this edit.
        clearListing(first, last);
        if (!disassemble(first)) throw new IllegalStateException("Cannot decode MPEG motion callback");
        for (long pc=0x12ae70; pc<0x12af04; pc+=4)
            if (getInstructionAt(toAddr(pc)) == null)
                throw new IllegalStateException("Incomplete MPEG motion callback disassembly");
        if (function == null) function = createFunction(first, "observed_mpeg_motion_0012ae70");
        if (function == null) throw new IllegalStateException("Cannot establish MPEG callback");
        function.setBody(new AddressSet(first, last));
        analyzeChanges(currentProgram);
        println("Verified and decoded all 37 original MPEG motion callback instructions");
    }
}
