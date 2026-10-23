// SPDX-License-Identifier: GPL-3.0-or-later
// Identify decoded PAL entries referenced by verified long interface tables.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashSet;

public class SeedLongInterfaceMethods extends GhidraScript {
    private static final long[] ENTRIES = {
        0x181d60,0x194dc0,0x1991d0,0x199430,0x1996b0,0x19fa20,0x19fa70,0x1a1a00,
        0x1a6340,0x1a7940,0x1adfe0,0x22d880,0x22d890,0x22d8c0,0x2383a0,0x23a5c0,
        0x257ff0,0x258000,0x258010,0x258020,0x258030,0x258040,0x258050,0x258060,
        0x25aac0,0x264dc0,0x264e10,0x267a20,0x26a9e0,0x274110,0x27ad90,0x27afd0,
        0x27afe0,0x27b000,0x29bfd0,0x2ab320,0x2cddf0,0x2ef950,0x31d9b0,0x35fb60,
        0x370760,0x374e30,0x374ea0,0x3a4340,0x3ad000,0x3b8b00,0x3bc2d0,0x3c3960,
        0x3c39e0,0x3c9140,0x3d69e0,0x3d6b00,0x3e9480,0x3f8a20,0x3ffea0,0x401290,
        0x403ff0,0x4042f0,0x4139c0,0x416060};

    private static boolean method(long value) {
        return (value & 3) == 0 && value >= 0x167c40L && value < 0x44ab60L;
    }

    public void run() throws Exception {
        byte[] resident = getBytes(toAddr(0x100000), 0x56280);
        ByteBuffer words = ByteBuffer.wrap(resident).order(ByteOrder.LITTLE_ENDIAN);
        MessageDigest catalog = MessageDigest.getInstance("SHA-256");
        LinkedHashSet<Long> methods = new LinkedHashSet<>();
        int tables = 0;
        // Two zero header words followed by at least eight aligned MAIN
        // method pointers. Each maximal nonzero pointer run is one record.
        for (int start = 0; start + 40 <= resident.length; start += 4) {
            monitor.checkCancelled();
            if (words.getInt(start) != 0 || words.getInt(start + 4) != 0) continue;
            int end = start + 8;
            while (end + 4 <= resident.length && method(Integer.toUnsignedLong(words.getInt(end)))) end += 4;
            if (end - start < 40) continue;
            ByteBuffer header = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN);
            header.putInt(0x100000 + start).putInt((end - start) / 4);
            catalog.update(header.array());
            catalog.update(resident, start, end - start);
            for (int offset = start + 8; offset < end; offset += 4)
                methods.add(Integer.toUnsignedLong(words.getInt(offset)));
            ++tables;
        }
        if (tables != 468 || methods.size() != 3460 || !HexFormat.of().formatHex(catalog.digest()).equals(
                "62e3ef92025d10c6d9e0b14af53e58ea38525cf7700652b168ade858ddf0deba"))
            throw new IllegalStateException("Original PAL long-interface catalog differs");
        for (long pc : methods) {
            Address address = toAddr(pc);
            var block = currentProgram.getMemory().getBlock(address);
            if (block == null || !block.isExecute() || !block.isInitialized() || getInstructionAt(address) == null)
                throw new IllegalStateException("Long-interface method is not decoded executable code");
        }
        MessageDigest code = MessageDigest.getInstance("SHA-256");
        for (long pc : ENTRIES) {
            Address address = toAddr(pc);
            var owner = getFunctionContaining(address);
            if (!methods.contains(pc) || getInstructionAt(address).isInDelaySlot() ||
                    (owner != null && !owner.getEntryPoint().equals(address)))
                throw new IllegalStateException("Long-interface entry conflicts with classified code");
            ByteBuffer record = ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN);
            record.putInt((int)pc).put(getBytes(address, 8));
            code.update(record.array());
        }
        if (!HexFormat.of().formatHex(code.digest()).equals(
                "9402351848bed51a0e6be05780536bdd32eabc2e741a51463c205170cf9585c9"))
            throw new IllegalStateException("Original PAL long-interface entry bytes differ");
        int created = 0;
        for (long pc : ENTRIES) {
            monitor.checkCancelled();
            Address address = toAddr(pc);
            if (getFunctionAt(address) == null) {
                if (getFunctionContaining(address) != null ||
                        createFunction(address, String.format("pal_long_interface_%08x", pc)) == null)
                    throw new IllegalStateException("Cannot identify decoded long-interface entry");
                ++created;
            }
        }
        analyzeChanges(currentProgram);
        println("Verified 468 original long tables / 3460 methods; identified " + created + " entries");
    }
}
