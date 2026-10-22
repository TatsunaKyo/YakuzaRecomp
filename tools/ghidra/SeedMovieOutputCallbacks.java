// SPDX-License-Identifier: GPL-3.0-or-later
// Identify missing entries in the original movie-output interfaces.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.MemoryBlock;
import java.security.MessageDigest;
import java.util.HashSet;

public class SeedMovieOutputCallbacks extends GhidraScript {
    private static final long[] TABLES = {0x4edbe0, 0x4edc18, 0x4edc60};
    private static final String[] HASHES = {
        "ac9a5012d68372e58124bb2042e7998bc0f18e004d7a46e77e45da3deb784ef1",
        "5766bfbff4c109b881e70adb84b69001bd424210df876d53dfa6a9f13971df7b",
        "45c8ce8c04801545675153ef4420069d9e3287dfff9b1ab59c48a2b8f86e3503"};
    private static final long[] ENTRIES = {0x1d6128,0x1d6168,0x1d6170,0x1d6178,0x1d6180,
        0x1d8008,0x1d8010,0x1d8018,0x1dd0d8,0x1dd0e0,0x1dd0e8};
    public void run() throws Exception {
        HashSet<Long> pointers = new HashSet<>();
        for (int index=0; index<TABLES.length; ++index) {
            byte[] bytes=getBytes(toAddr(TABLES[index]),56);
            StringBuilder hex=new StringBuilder();
            for(byte value:MessageDigest.getInstance("SHA-256").digest(bytes))
                hex.append(String.format("%02x",value&255));
            if(!hex.toString().equals(HASHES[index]))
                throw new IllegalStateException("Original movie-output table differs");
            for(int slot=0;slot<14;++slot) {
                long pc=Integer.toUnsignedLong(getInt(toAddr(TABLES[index]+slot*4)));
                Address address=toAddr(pc);
                MemoryBlock block=currentProgram.getMemory().getBlock(address);
                if((pc&3)!=0 || pc<0x100008 || pc>=0x592080 || block==null ||
                    !block.isExecute() || !block.isInitialized() || getInstructionAt(address)==null)
                    throw new IllegalStateException("Movie-output pointer is not decoded executable code");
                pointers.add(pc);
            }
        }
        for(long pc:ENTRIES) {
            Function owner=getFunctionContaining(toAddr(pc));
            if(!pointers.contains(pc) || (owner!=null && !owner.getEntryPoint().equals(toAddr(pc))))
                throw new IllegalStateException("Movie-output callback conflicts with classified code");
        }
        int created=0;
        for(long pc:ENTRIES) if(getFunctionAt(toAddr(pc))==null) {
            if(createFunction(toAddr(pc),String.format("movie_output_%08x",pc))==null)
                throw new IllegalStateException("Cannot identify movie-output callback");
            ++created;
        }
        analyzeChanges(currentProgram);
        println("Verified 42 movie-output pointers; newly identified callbacks: "+created);
    }
}
