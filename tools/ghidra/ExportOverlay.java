// Export initialized, executable instructions without spanning typed data.
// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import java.io.PrintWriter;
import java.security.MessageDigest;
import java.util.ArrayList;

public class ExportOverlay extends GhidraScript {
    private static class Range {
        String name;
        long start;
        long end;
        long owner;
        Range(String name, long start, long end, long owner) {
            this.name = name; this.start = start; this.end = end; this.owner = owner;
        }
    }

    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 5) throw new IllegalArgumentException("Expected CSV, JSON, start, end and prefix");
        ArrayList<Range> ranges = new ArrayList<>();
        Range range = null;
        long instructionCount = 0;
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext()) {
            monitor.checkCancelled();
            Instruction instruction = it.next();
            Address address = instruction.getAddress();
            MemoryBlock block = currentProgram.getMemory().getBlock(address);
            if (block == null || !block.isExecute() || !block.isInitialized()) continue;
            long start = address.getOffset();
            if (start < Long.parseLong(args[2]) || start >= Long.parseLong(args[3])) continue;
            if (instruction.getLength() != 4) throw new IllegalStateException("Non-R5900 instruction length");
            Function function = currentProgram.getFunctionManager().getFunctionContaining(address);
            Function entry = currentProgram.getFunctionManager().getFunctionAt(address);
            long owner = function == null ? -1 : function.getEntryPoint().getOffset();
            if (range == null || start != range.end || owner != range.owner || entry != null) {
                String name = entry == null ? String.format("decoded_chunk_%08X", start) : entry.getName().replace(',', '_');
                range = new Range(args[4] + "_" + name, start, start + 4, owner);
                ranges.add(range);
            } else {
                range.end = start + 4;
            }
            for (int shift = 0; shift < 32; shift += 8) digest.update((byte)(start >>> shift));
            digest.update(instruction.getBytes());
            instructionCount++;
        }
        if (instructionCount == 0) throw new IllegalStateException("No decoded instructions");
        long coveredBytes = 0;
        long previousEnd = 0;
        try (PrintWriter out = new PrintWriter(args[0])) {
            out.println("Name,Start,End,Size");
            for (Range item : ranges) {
                if (item.start < previousEnd || item.end <= item.start) throw new IllegalStateException("Invalid decoded ranges");
                out.printf("%s,0x%08X,0x%08X,%d%n", item.name, item.start, item.end, item.end - item.start);
                coveredBytes += item.end - item.start;
                previousEnd = item.end;
            }
        }
        if (coveredBytes != instructionCount * 4) throw new IllegalStateException("Decoded instruction coverage mismatch");
        StringBuilder hex = new StringBuilder();
        for (byte value : digest.digest()) hex.append(String.format("%02x", value & 255));
        try (PrintWriter out = new PrintWriter(args[1])) {
            out.printf("{\"range_count\":%d,\"instruction_count\":%d,\"covered_bytes\":%d,\"address_and_instruction_sha256\":\"%s\",\"scope\":\"initialized executable instructions decoded in this overlay; unknown code is not established\"}%n",
                ranges.size(), instructionCount, coveredBytes, hex.toString());
        }
        println("Decoded PAL ranges: " + ranges.size() + "; instructions: " + instructionCount + "; bytes: " + coveredBytes);
    }
}
