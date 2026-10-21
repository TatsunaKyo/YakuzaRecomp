// SPDX-License-Identifier: GPL-3.0-or-later
// Identify an entry reached or referenced while a verified MWo3 overlay is active.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.CodeUnit;

public class SeedOverlayIndirect extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) throw new IllegalArgumentException("Expected target and original first instruction");
        long target = Long.decode(args[0]), expected = Long.decode(args[1]);
        long base = 0x62dc80L;
        if (getInt(toAddr(base)) != 0x336f574d || getInt(toAddr(base + 8)) != base)
            throw new IllegalStateException("Missing original PAL gameplay overlay header");
        long end = base + 64 + Integer.toUnsignedLong(getInt(toAddr(base + 12))) +
            Integer.toUnsignedLong(getInt(toAddr(base + 16)));
        if (end > 0x6ef500L || (target & 3) != 0 || target < base + 64 || target + 4 > end)
            throw new IllegalStateException("Observed target is outside the initialized overlay");
        var entry = toAddr(target);
        if (Integer.toUnsignedLong(getInt(entry)) != expected)
            throw new IllegalStateException("Original overlay instruction differs");
        if (getFunctionAt(entry) == null) {
            if (getFunctionContaining(entry) != null)
                throw new IllegalStateException("Observed target conflicts with a classified function");
            clearListing(entry, entry.add(3));
            if (!disassemble(entry) || createFunction(entry, String.format("observed_overlay_%08x", target)) == null)
                throw new IllegalStateException("Cannot identify original overlay target");
        }
        currentProgram.getListing().setComment(entry, CodeUnit.PLATE_COMMENT,
            "Original entry from a verified boot target or method table; bytes preserved.");
        analyzeChanges(currentProgram);
        println("Identified observed original overlay entry " + entry);
    }
}
