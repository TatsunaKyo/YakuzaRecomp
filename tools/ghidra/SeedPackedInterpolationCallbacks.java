// SPDX-License-Identifier: GPL-3.0-or-later
// Classify the original packed-track variants selected by PAL routine 0x248df0.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.CodeUnit;
import java.security.MessageDigest;
import java.util.HexFormat;

public class SeedPackedInterpolationCallbacks extends GhidraScript {
    private void verifyOriginal() throws Exception {
        byte[] original = getBytes(toAddr(0x248df0L), 0x950);
        String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(original));
        if (!actual.equals("335659a2b95cfbd130445e497d907e2c06aef4229e139c591837edf971b4db06"))
            throw new IllegalStateException("Original PAL interpolation selector or wrappers differ");
    }

    public void run() throws Exception {
        // The digest covers the complete selector and all eight wrappers,
        // including its immediate-address choices before the JALR sites.
        // Native execution observed 0x249298 -> 0x249320 after stage loading.
        verifyOriginal();
        long[] entries = {0x249320L, 0x2493a0L, 0x249430L, 0x2494b0L,
                          0x249540L, 0x2495c0L, 0x249640L, 0x2496c0L};
        // Reject every conflict before changing any function metadata.
        for (long target : entries) {
            var entry = toAddr(target);
            var block = currentProgram.getMemory().getBlock(entry);
            if (block == null || !block.isExecute() ||
                    (getFunctionAt(entry) == null && getFunctionContaining(entry) != null))
                throw new IllegalStateException("PAL interpolation entry conflicts with classified code: " + entry);
        }
        int created = 0;
        for (long target : entries) {
            monitor.checkCancelled();
            var entry = toAddr(target);
            if (getFunctionAt(entry) != null) continue;
            if (getFunctionContaining(entry) != null)
                throw new IllegalStateException("PAL interpolation entry conflicts with newly classified code: " + entry);
            clearListing(entry, entry.add(3));
            if (!disassemble(entry) ||
                    createFunction(entry, String.format("pal_packed_interpolation_%08x", target)) == null)
                throw new IllegalStateException("Could not classify original PAL interpolation entry: " + entry);
            currentProgram.getListing().setComment(entry, CodeUnit.PLATE_COMMENT,
                "Original immediate-address callback selected by SHA-256-verified PAL routine 0x248df0; bytes preserved.");
            ++created;
        }
        analyzeChanges(currentProgram);
        verifyOriginal();
        println("Verified 8 original PAL packed interpolation wrappers; identified " + created + " new entries");
    }
}
