"""Exercise the real CMD launcher using an original-free runtime fixture."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--exe", required=True, type=Path)
parser.add_argument("--launcher", required=True, type=Path)
args = parser.parse_args()
if os.name != "nt":
    raise SystemExit("This check requires the Windows command interpreter")

required = {
    "SYSTEM.CNF", "SLES_541.71", "MAIN.BIN", "IRX.DAT", "IOPRP300.IMG",
    "PAL_NTSC.DAT", "OGRE.CVM", "OGRE2.CVM", "OGRE3.CVM", "OGRE4.CVM",
    "OGREDIR.BIN", "OGREDIR2.BIN", "OGREDIR3.BIN", "OGREDIR4.BIN",
}

with tempfile.TemporaryDirectory(prefix="yakuza-launcher-") as temporary:
    root = Path(temporary)
    package = root / "Package with spaces"
    disc = root / "Disc with spaces (PAL) & data"
    package.mkdir()
    disc.mkdir()
    launcher = package / "Run-Yakuza.cmd"
    launcher.write_bytes(args.launcher.read_text().replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii"))
    shutil.copy2(args.exe, package / "YakuzaRecomp-test.exe")
    for name in ["SYSTEM.CNF", "SLES_541.71", "MAIN.BIN", "IRX.DAT"]:
        (disc / name).write_bytes(b"owned synthetic fixture")
    env = os.environ.copy()
    env["YAKUZA_LAUNCHER_NO_PAUSE"] = "1"
    command = subprocess.list2cmdline([str(launcher), str(disc)])
    result = subprocess.run(command, shell=True, input="", capture_output=True, text=True, env=env, timeout=20)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    log = (package / "native-test.log").read_text()
    missing = {line.split("=", 1)[1] for line in log.splitlines() if line.startswith("[launcher] missing_file=")}
    assert missing == required - {"SYSTEM.CNF", "SLES_541.71", "MAIN.BIN", "IRX.DAT"}, missing
    assert "Unsupported PAL input size" not in log
    assert (package / "exit-code.txt").read_text().strip() == "2"

    # All names exist, but the deliberately invalid boot bytes must reach the
    # fixture's own input validation. A trailing slash must not merge argv.
    for name in required:
        (disc / name).touch(exist_ok=True)
    result = subprocess.run(str(launcher), shell=True, input='"'+str(disc)+'\\"\n', capture_output=True, text=True, env=env, timeout=20)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    log = (package / "native-test.log").read_text()
    assert "Unsupported PAL input size" in log, log
    assert "[launcher] missing_file=" not in log
    assert "[launcher] exit_code=2" in log
    assert (package / "exit-code.txt").read_text().strip() == "2"

print("Windows launcher rejects partial disc folders and preserves trailing-slash arguments")
