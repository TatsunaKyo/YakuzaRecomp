// Classify verified original GAME bytes using the catalog recovered from the PE.
// This creates a fresh analysis, not a recovered historical decoded map.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.HashSet;

public class SeedRecoveredGame extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) throw new IllegalArgumentException("Expected recovered owners and callable addresses");
        byte[] original = getBytes(toAddr(0x62dc80L), 704896);
        String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(original));
        if (!digest.equals("64b6d4f666a321e682be6becc6d89b37d6c171f0ff3448950a19e7c2ee590c37"))
            throw new IllegalStateException("Original GAME image differs");
        byte[] seedBytes = Files.readAllBytes(Path.of(args[0]));
        if (!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(seedBytes)).equals(
                "e517ce8aba413192ec06e7c1be67889aec47a9e8d75685dd794c3283f8815560"))
            throw new IllegalStateException("Recovered owner/new-table seed list differs");
        if (!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(Path.of(args[1])))).equals(
                "2c1c3d23c5d50d9d8f96cdc60322ccf9327214f4207989dc185e4eb45b6e30db"))
            throw new IllegalStateException("Actual recovered callable list differs");
        int created = 0, contained = 0;
        HashSet<Long> seen = new HashSet<>();
        for (String line : Files.readAllLines(Path.of(args[0]))) {
            monitor.checkCancelled();
            String[] fields = line.split(" ", 2);
            long value = Long.parseUnsignedLong(fields[0], 16);
            if (!seen.add(value) || (value & 3) != 0 || value < 0x62dcc0L || value >= 0x6d9e00L)
                throw new IllegalStateException("Invalid recovered entry");
            Address entry = toAddr(value);
            if (getInstructionAt(entry) == null) disassemble(entry);
            if (getInstructionAt(entry) == null) throw new IllegalStateException("Cannot decode original entry " + entry);
            Function function = getFunctionAt(entry);
            if (function == null && getFunctionContaining(entry) == null) {
                function = createFunction(entry, fields[1]);
                if (function == null) throw new IllegalStateException("Cannot classify original entry " + entry);
                ++created;
            } else if (function == null) {
                createLabel(entry, fields[1], true, SourceType.USER_DEFINED);
                ++contained;
            }
            if (function != null) function.setName(fields[1], SourceType.USER_DEFINED);
        }
        if (seen.size() != 1987) throw new IllegalStateException("Unexpected recovered owner/new-method count");
        int aliases = 0;
        for (String line : Files.readAllLines(Path.of(args[1]))) {
            monitor.checkCancelled();
            Address entry = toAddr(Long.parseUnsignedLong(line, 16));
            if (getInstructionAt(entry) == null) disassemble(entry);
            if (getInstructionAt(entry) == null) throw new IllegalStateException("Cannot decode old callable address " + entry);
            ++aliases;
        }
        if (aliases != 95309) throw new IllegalStateException("Unexpected recovered callable count");
        if (!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(getBytes(toAddr(0x62dc80L),704896))).equals(digest))
            throw new IllegalStateException("Analysis changed original bytes");
        println("Recovered GAME seeds: " + seen.size() + "; created: " + created + "; contained starts: " + contained + "; verified old callable addresses: " + aliases);
    }
}
