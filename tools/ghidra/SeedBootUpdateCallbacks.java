// SPDX-License-Identifier: GPL-3.0-or-later
// Classify original PAL object method tables reached during boot.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashSet;

public class SeedBootUpdateCallbacks extends GhidraScript {
    private final LinkedHashSet<Long> verifiedTables = new LinkedHashSet<>();
    private void collectCatalog(int wordCount, long finalMethod, int expectedTables,
            int expectedMethods, String expectedDigest, LinkedHashSet<Long> allEntries,
            long... explicitTables) throws Exception {
        // Scan only PAL resident bytes; accept methods in MAIN's primary text.
        // The digest covers each table address followed by all table words,
        // in ascending address order, encoded as little-endian uint32s.
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        LinkedHashSet<Long> entries = new LinkedHashSet<>();
        LinkedHashSet<Long> tables = new LinkedHashSet<>();
        int tableCount = 0;
        boolean explicit = explicitTables.length != 0;
        long candidates = explicit ? explicitTables.length : (0x56280L - wordCount * 4L) / 4 + 1;
        for (long index = 0; index < candidates; ++index) {
            monitor.checkCancelled();
            long table = explicit ? explicitTables[(int)index] : 0x100000L + index * 4;
            if ((table & 3) != 0 || table < 0x100000L || table + wordCount * 4L > 0x156280L ||
                    (explicit && index > 0 && table <= explicitTables[(int)index - 1]))
                throw new IllegalStateException("Invalid PAL method table location");
            if (getInt(toAddr(table)) != 0 || getInt(toAddr(table + 4)) != 0 ||
                    (!explicit && Integer.toUnsignedLong(getInt(toAddr(table + (wordCount - 1) * 4L))) != finalMethod)) continue;
            long[] words = new long[wordCount];
            boolean valid = true;
            for (int i = 2; i < wordCount; ++i) {
                words[i] = Integer.toUnsignedLong(getInt(toAddr(table + i * 4L)));
                if ((words[i] & 3) != 0 || words[i] < 0x167c40L || words[i] >= 0x44ab60L)
                    valid = false;
            }
            if (!valid) continue;
            ByteBuffer record = ByteBuffer.allocate((wordCount + 1) * 4).order(ByteOrder.LITTLE_ENDIAN);
            record.putInt((int)table);
            for (long word : words) record.putInt((int)word);
            digest.update(record.array());
            ++tableCount;
            tables.add(table);
            for (int i = 2; i < wordCount; ++i) entries.add(words[i]);
        }
        if (tableCount != expectedTables || entries.size() != expectedMethods ||
                !HexFormat.of().formatHex(digest.digest()).equals(expectedDigest))
            throw new IllegalStateException("Original PAL update method catalog differs");
        allEntries.addAll(entries);
        verifiedTables.addAll(tables);
    }

    public void run() throws Exception {
        LinkedHashSet<Long> entries = new LinkedHashSet<>();
        // Two zero header words precede the methods in these observed families.
        // Update objects share final method 0x26ea10; draw objects use 0x29e4b0.
        collectCatalog(7, 0x26ea10L, 240, 663,
            "1f548812c68d61eacc37374e7e19346f0b1d813ab4fe064497c0a4dbc9726936", entries);
        collectCatalog(6, 0x29e4b0L, 11, 23,
            "93d54ecebb7110ac4c85b3e3711949d0b31c52b9e39cec976fd3462eaa2c0132", entries);
        // Interfaces reached after CSE_STAY.DAT, SEGALOGO.DAT and
        // TALK_MEMCARD.BIN use distinct final methods. Verify complete tables.
        collectCatalog(7, 0, 5, 24,
            "f4bccc7631010e1b2a67496a39abc7cd839d579800f6c5b79037833396e96170", entries,
            0x13d5d0L, 0x13d5f0L, 0x13d610L, 0x13da00L, 0x13dad0L);
        // The object at 0x157458 exposes the first two of these adjacent
        // small interfaces in the observed boot trace. Verify all three.
        collectCatalog(5, 0, 3, 9,
            "1744351a7c07ad76175f068618a41c1177c9b0da92433357b50cb5cd4a478ae7", entries,
            0x1427e0L, 0x142800L, 0x142820L);
        // This larger interface is reached after the memory-card message load.
        collectCatalog(31, 0, 1, 29,
            "d0abe1bd38ce9377a47151d78b9fb500f01857941aa669b951a5e32d04b1070a", entries,
            0x13da20L);
        // Opening-scene execution reaches this 46-method interface after
        // loading OPENING_MOVIE.DAT and its B00 companion.
        collectCatalog(48, 0, 1, 46,
            "c2df386a06ebe5d6f8940e54a609d75f863bf2f4de402551ea69df49b5384361", entries,
            0x13d770L);
        // Adjacent one-method interfaces, including the table used by the
        // observed callback at 0x1a2910 on the opening-scene path.
        collectCatalog(3, 0, 3, 3,
            "99c3da5e42d8f6898214d817820d712e6f1acd112e29483ab3c16ce2ea132306", entries,
            0x13b340L, 0x13b350L, 0x13b360L);
        // Stage-resource loading reaches the reference-count method in this
        // five-method interface. Verify both headers and the complete table.
        collectCatalog(7, 0, 1, 5,
            "a4064fd42c263a9ea80c2b432763954cf4fc9d504990f3d20aa16a00a91428b0", entries,
            0x13b570L);
        // New Game reaches the shared final method of this menu-phase
        // family. Fingerprint every complete three-method table.
        collectCatalog(5, 0x230d40L, 17, 27,
            "3a121408a13ff24dd597d7031ae0069fa532e9763ae71efe0650703868d18d9c", entries);
        // Dojima loading reaches slot 0x18 in the first of these five-method
        // interfaces. All sixteen share 0x24c7e0 as their first method.
        collectCatalog(7, 0, 16, 65,
            "eeabfa0c0111d9ddcb0f148413081cb420a7f707d25b4994d76f790ea7abe20d", entries,
            0x13d900L, 0x13d920L, 0x13d940L, 0x13d960L, 0x13d980L, 0x13d9a0L,
            0x13d9c0L, 0x13d9e0L, 0x13da00L, 0x1421a0L, 0x143580L, 0x1435f0L,
            0x1436f0L, 0x1444a0L, 0x144630L, 0x146a20L);
        // Validate the entire catalog before changing any analysis metadata.
        for (long target : entries) {
            Address entry = toAddr(target);
            var block = currentProgram.getMemory().getBlock(entry);
            if (block == null || !block.isExecute())
                throw new IllegalStateException("Update callback is outside executable memory");
            if (getFunctionAt(entry) == null && getFunctionContaining(entry) != null)
                throw new IllegalStateException("Update callback conflicts with a classified function: " + entry);
        }
        int created = 0;
        for (long target : entries) {
            monitor.checkCancelled();
            Address entry = toAddr(target);
            if (getFunctionAt(entry) == null) {
                if (getFunctionContaining(entry) != null)
                    throw new IllegalStateException("Update callback conflicts with a newly classified function: " + entry);
                clearListing(entry, entry.add(3));
                if (!disassemble(entry) ||
                        createFunction(entry, String.format("pal_boot_update_%08x", target)) == null)
                    throw new IllegalStateException("Could not classify original update callback: " + entry);
                currentProgram.getListing().setComment(entry, CodeUnit.PLATE_COMMENT,
                    "Original PAL method from SHA-256-verified boot update table catalog; bytes preserved.");
                println(String.format("Identified PAL update entry 0x%08x", target));
                ++created;
            }
        }
        analyzeChanges(currentProgram);
        println("Verified " + verifiedTables.size() + " distinct original PAL tables / " + entries.size() + " methods; identified " + created + " new entries");
    }
}
