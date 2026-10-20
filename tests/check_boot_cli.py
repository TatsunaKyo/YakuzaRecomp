"""Check that the built host rejects invalid input before creating a window."""
from pathlib import Path
import subprocess
import sys
import tempfile

exe = str(Path(sys.argv[1]).resolve())


def rejects(arguments, message):
    result = subprocess.run([exe, *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=10)
    assert result.returncode == 2, result.stdout
    assert message in result.stdout, result.stdout
    assert "Initializing raylib" not in result.stdout, result.stdout


rejects([], "Usage:")
with tempfile.TemporaryDirectory(prefix="Yakuza PAL ü ") as folder:
    rejects([folder], "must contain SLES_541.71 and MAIN.BIN")
    root = Path(folder)
    (root / "SLES_541.71").write_bytes(b"not an ELF")
    (root / "MAIN.BIN").write_bytes(b"not a game overlay")
    rejects([folder], "Unsupported PAL input size")
    rejects([folder, "0"], "Time limit must be 1..120 seconds")
print("Boot host CLI rejected missing, truncated and invalid-limit inputs before graphics startup")
