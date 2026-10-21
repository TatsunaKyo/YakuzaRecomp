#!/usr/bin/env python3
"""Package the Windows diagnostic with source and licenses, without game data."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile

PIN = "eb8688b2fd191129f103a39543002c005b33409c"
SOURCE_FILES = [
    ".gitignore", ".github/workflows/checks.yml", "CMakeLists.txt", "COPYING", "README.md",
    "THIRD_PARTY_NOTICES.md", "cmake/windows-llvm-mingw.cmake", "docs/windows-testing.md",
    "licenses/YakuzaPythonExtractor-MIT.txt", "tests/test_formats.py",
    "tools/iop_probe.cpp", "tools/prepare_game.py", "tools/package_diagnostic.py",
    "docs/overlays.md", "tools/overlay_image.py", "tools/overlay_native_probe.cpp",
    "tools/ghidra/SeedOverlay.java", "tools/ghidra/ExportOverlay.java", "tools/ghidra/SeedResidentCtor.java",
    "tools/ghidra/SeedGraphicsEntry.java", "tools/prepare_runtime.py", "config/pal-runtime-layout.json",
    "tools/ghidra/SeedObservedEntry.java",
    "include/yakuza/overlay_slot.h", "src/overlay_slot.cpp",
    "include/yakuza/native_pad.h", "src/native_pad.cpp", "tests/test_native_pad.cpp",
    "include/yakuza/disc_ranges.h", "src/disc_ranges.cpp", "tools/disc_ranges.py",
    "tests/test_disc_ranges.cpp", "tests/test_disc_ranges.py", "tests/test_disc_ranges_iso.py", "docs/disc-ranges.md",
    "tests/test_overlay_image.py", "tests/test_overlay_slot.cpp",
    "cmake/boot-probe.cmake", "docs/boot-probe.md", "include/yakuza/pal_boot_hooks.h",
    "src/pal_boot_hooks.cpp", "tools/boot_probe.cpp", "tools/prepare_boot.py", "tools/run_boot_probe.py", "tools/prepare_boot_supplement.py",
    "tests/test_prepare_boot.py", "tests/check_boot_cli.py", "tests/test_boot_dispatch.cpp",
    "tests/fixtures/boot-host/register_functions.cpp", "tests/fixtures/boot-host/synthetic_entry.cpp",
    "tests/fixtures/boot-host/ps2_recompiled_functions.h", "tests/fixtures/boot-host/ps2_recompiled_stubs.h",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--dependency-dir", required=True, type=Path)
    parser.add_argument("--toolchain-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    binary = args.exe.read_bytes()
    if binary[:2] != b"MZ" or len(binary) < 64:
        raise ValueError("Expected a Windows PE executable")
    pe = struct.unpack_from("<I", binary, 60)[0]
    if binary[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", binary, pe + 4)[0] != 0x8664:
        raise ValueError("Expected a Windows x86-64 executable")
    revision = subprocess.check_output(["git", "-C", str(args.dependency_dir), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(args.dependency_dir), "status", "--porcelain"], text=True)
    if revision != PIN or dirty:
        raise ValueError("Dependency source must match the clean pinned revision")
    upstream = subprocess.check_output(["git", "-C", str(args.dependency_dir), "archive", "--format=zip", "--prefix=PS2Recomp/", PIN])
    runtime = args.toolchain_dir / "x86_64-w64-mingw32/share/mingw32"
    licenses = [args.toolchain_dir / "LICENSE.TXT", *sorted(runtime.glob("COPYING*"))]
    if not all(path.is_file() for path in licenses) or len(licenses) < 2:
        raise ValueError("Required cross-toolchain runtime license files are missing")
    for name in SOURCE_FILES:
        if not (source / name).is_file(): raise ValueError(f"Missing project source: {name}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists(): raise ValueError("Choose a new output filename; existing artifacts are preserved")
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("yakuza_iop_probe.exe", binary)
        package.writestr("source/PS2Recomp-source.zip", upstream)
        for name in SOURCE_FILES: package.write(source / name, "source/YakuzaRecomp/" + name)
        for path in licenses: package.write(path, "licenses/" + path.name)
        package.write(source / "COPYING", "COPYING")
        package.writestr("build-info.json", json.dumps({
            "target": "Windows 10/11 x64", "purpose": "IOP diagnostic, not a game executable",
            "windows_runtime_tested": False, "dependency_revision": PIN,
            "exe_sha256": hashlib.sha256(binary).hexdigest(),
            "toolchain": "LLVM-MinGW 20261006 UCRT, Clang 23.1.3",
        }, indent=2) + "\n")
        package.writestr("READ_ME.txt", """Yakuza PAL IOP diagnostic for Windows 10/11 x64

This is a development diagnostic, not the game. No game data is included.
The executable was cross-built on Linux; actual Windows execution is pending.

In PowerShell, from this extracted folder:
  .\\yakuza_iop_probe.exe "D:\\Yakuza PAL\\IRX.DAT" > probe.txt 2>&1

IRX.DAT stays unchanged. The Linux baseline loads nine original driver modules,
registering eight RPC servers and 15 threads. Audio, controller operation,
memory cards, game boot, graphics and gameplay remain unverified.

Project source is in source/YakuzaRecomp. Extract source/PS2Recomp-source.zip
to obtain the exact unmodified dependency source. Native Windows/MSVC build
instructions are in source/YakuzaRecomp/README.md. COPYING and licenses retain
the applicable third-party notices. No Linux or WSL installation is needed.
""")
    print(args.output)
    print("ZIP bytes:", args.output.stat().st_size)
    print("ZIP SHA256:", hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == "__main__": main()
