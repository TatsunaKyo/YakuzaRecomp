// SPDX-License-Identifier: GPL-3.0-or-later
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class SeedGraphicsEntry extends GhidraScript {
    public void run() throws Exception {
        Address entry = toAddr(0x18fda0L);
        if (getInt(toAddr(0x13a914L)) != 0x18fda0)
            throw new IllegalStateException("PAL graphics vtable differs");
        if (getFunctionAt(entry) == null) {
            if (getFunctionContaining(entry) != null)
                throw new IllegalStateException("Conflicting graphics function");
            clearListing(entry, toAddr(0x18fda8L));
            if (!disassemble(entry) || createFunction(entry, "FUN_0018fda0") == null)
                throw new IllegalStateException("Could not seed graphics vtable entry");
        }
        analyzeChanges(currentProgram);
        println("Analyzed graphics vtable entry at " + entry);
    }
}
