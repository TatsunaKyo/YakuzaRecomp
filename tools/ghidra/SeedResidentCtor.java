// SPDX-License-Identifier: GPL-3.0-or-later
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class SeedResidentCtor extends GhidraScript {
    public void run() throws Exception {
        Address first = toAddr(0x13a2a0L), last = toAddr(0x13a2f7L);
        if (getInt(toAddr(0x13a304L)) != 0x13a2a0)
            throw new IllegalStateException("Resident constructor table differs");
        if (getFunctionAt(first) == null) {
            if (getFunctionContaining(first) != null)
                throw new IllegalStateException("Conflicting containing function");
            // Change analysis metadata only. Preserve every original byte.
            clearListing(first, last);
            if (!disassemble(first) || createFunction(first, "FUN_0013a2a0") == null)
                throw new IllegalStateException("Could not seed resident constructor");
        }
        analyzeChanges(currentProgram);
        println("Analyzed previously unseeded resident constructor at " + first);
    }
}
