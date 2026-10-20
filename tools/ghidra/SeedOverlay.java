// @category YakuzaResearch
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import java.nio.file.Files;
import java.nio.file.Path;

public class SeedOverlay extends GhidraScript {
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) throw new IllegalArgumentException("Expected seed file and module prefix");
        int count = 0;
        for (String line : Files.readAllLines(Path.of(args[0]))) {
            String[] fields = line.split(" ");
            Address address = toAddr(Long.parseUnsignedLong(fields[0], 16));
            disassemble(address);
            Function function = getFunctionAt(address);
            String name = args[1] + "_" + fields[1];
            if (function == null) function = createFunction(address, name);
            if (function == null) throw new IllegalStateException("Cannot seed " + address);
            function.setName(name, SourceType.USER_DEFINED);
            count++;
        }
        println("Overlay seeded functions: " + count);
    }
}
