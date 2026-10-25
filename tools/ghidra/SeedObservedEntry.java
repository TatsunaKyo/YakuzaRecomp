// SPDX-License-Identifier: GPL-3.0-or-later
// Seed only a target observed in a verified original-code runtime trace.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;

public class SeedObservedEntry extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) throw new IllegalArgumentException("Expected target and original first instruction word");
        long target = Long.decode(args[0]), word = Long.decode(args[1]);
        if ((target & 3) != 0 || target < 0x100008 || target >= 0x592080)
            throw new IllegalStateException("Target is outside PAL resident/MAIN analysis");
        Address entry = toAddr(target);
        if (Integer.toUnsignedLong(getInt(entry)) != word)
            throw new IllegalStateException("Original instruction differs from observed PAL input");
        if (getFunctionAt(entry) == null) {
            if (getFunctionContaining(entry) != null)
                throw new IllegalStateException("Observed target conflicts with a classified function");
            clearListing(entry, entry.add(3));
            if (!disassemble(entry) || createFunction(entry, String.format("observed_boot_%08x", target)) == null)
                throw new IllegalStateException("Could not seed observed call target");
        }
        currentProgram.getListing().setComment(entry, CodeUnit.PLATE_COMMENT,
            "Call entry observed in a SHA-256-verified PAL native boot trace; original bytes preserved.");
        analyzeChanges(currentProgram);
        println("Analyzed observed PAL call entry " + entry);
    }
}
