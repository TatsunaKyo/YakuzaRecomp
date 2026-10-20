# Windows target and validation

The intended game target is Windows 10/11 x64. Linux is an internal development platform. A Linux test pass is never reported as a Windows runtime test.

Current evidence:

| Check | Result |
| --- | --- |
| Native Linux build and 23 Python format tests | Passed |
| Overlay loader swapping, bounds and BSS tests on Linux | Passed |
| Original 11 overlays loaded into RAM; three translated routines on Linux | 768 cases passed; hardware/constructors/gameplay untested |
| Four upstream IOP test programs on Linux | Passed |
| Original PAL IRX.DAT in the Linux diagnostic runtime | Nine modules resident; eight RPC servers, 15 threads |
| LLVM-MinGW cross-build of the diagnostic for Windows x64 | Passed |
| LLVM-MinGW cross-build of overlay tests and translated routine probe | Passed; execution pending |
| Windows PE inspection | x86-64 console executable; only Windows system/UCRT DLL imports |
| Execution on actual Windows | Pending |
| GitHub Actions Windows/MSVC build and tests | Configured, not yet run |
| Game boot, rendering, sound, input and gameplay | Pending |

## Running the Windows diagnostic

The diagnostic is a development tool, not the game. It reads IRX.DAT without changing it and runs the original drivers in a minimal IOP host. It does not provide audio output, a real controller or memory-card behavior.

Unzip the diagnostic package, open PowerShell in that folder, and run:

```powershell
.\yakuza_iop_probe.exe "D:\Yakuza PAL\IRX.DAT" > probe.txt 2>&1
```

The Linux baseline ends with nine loaded modules, 15 threads and eight RPC servers. Start results 0 and 2 both represent resident modules. A driver initialization message about SIF not being initialized is present in the minimal-host baseline; full EE/IOP SIF integration has not been tested.

If testing is requested on Windows, the useful result is probe.txt plus the program's exit code and Windows version. There is no need for the player to install Linux or WSL.

## Reproducing the Linux-to-Windows build

The cross-build uses LLVM-MinGW release 20261006, UCRT, Ubuntu 22.04 host package. Its published SHA-256 is 5f9c6ed95b2d4bdb2869a488c5fd5857fbdabcf288a0aa3eb1da43f6a08d8ab4. It is downloaded from the official mstorsjo/llvm-mingw GitHub release and verified before extraction.

```sh
cmake -S . -B out/cross -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=cmake/windows-llvm-mingw.cmake \
  -DYAKUZA_LLVM_MINGW_ROOT=/path/to/verified/llvm-mingw \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
cmake --build out/cross --parallel 2
```

This produces yakuza_iop_probe.exe and does not execute it. Use the native Windows build in README.md for MSVC and Windows test execution.

With the private verified analysis outputs present, passing `-DYAKUZA_OVERLAY_ANALYSIS_DIR=/path/to/overlay-analysis-v1` also builds `yakuza_overlay_native_probe.exe`. It uses three generated game routines and reads the eleven original module files. It is a RAM-only diagnostic, not a game executable. No full-runtime graphics/audio dependencies are linked into this probe. See [overlay research](overlays.md).
