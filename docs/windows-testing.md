# Windows target and validation

The intended game target is Windows 10/11 x64. Linux is an internal development platform. A Linux test pass is never reported as a Windows runtime test.

Current evidence:

| Check | Result |
| --- | --- |
| Native Linux build and 57 Python tests | Passed |
| Overlay loader swapping, bounds and BSS tests on Linux | Passed |
| Original 11 overlays loaded into RAM; three translated routines on Linux | 768 cases passed; hardware/constructors/gameplay untested |
| Four upstream IOP test programs on Linux | Passed |
| Original PAL IRX.DAT in the Linux diagnostic runtime | Nine modules resident; eight RPC servers, 15 threads |
| LLVM-MinGW cross-build of the diagnostic for Windows x64 | Passed |
| LLVM-MinGW cross-build of overlay tests and translated routine probe | Passed; execution pending |
| Windows PE inspection | x86-64 console executable; only Windows system/UCRT DLL imports |
| Original game execution on actual Windows | Pending |
| GitHub Actions Windows/MSVC and Linux default build and tests | Passed for 64425c2; [run](https://github.com/TatsunaKyo/YakuzaRecomp/actions/runs/39945232867) |
| Full-runtime Windows/MSVC host build and eight host checks | Passed with synthetic code, including IPU block/IDCT, color conversion and scratchpad DMA checks; same CI run |
| IPU MPEG blocks and RGB32 conversion on Linux and Windows cross-build | Golden pixel and DMA checks pass on Linux; Windows x64 host/test executables cross-build. Original movie playback remains unverified |
| Scratchpad source-chain DMA and native error regression | Failed before the correction; passes on Linux and Windows/MSVC CI. The original-code Windows host cross-builds; actual game execution remains pending |
| Full-runtime resident/MAIN and complete GAME boot-probe cross-link | Passed on Linux and Windows x64 |
| Original PAL loader to verified MAIN entry on Linux | Passed; continued execution loads GAME and reaches the opening-movie read |
| Original MAIN disc read, DMA and IOP module-start path on Linux | All nine IRX.DAT drivers started |
| Original memory-card dialog on Linux | Readable; complete 32 KiB glyph texture and 64-byte palette match original EE upload sources |
| Verified movie-driver interfaces in the original-code host | Linux and Windows x64 cross-link with all 98 method slots registered. Linux passes the observed callbacks and reaches the next mission-data read after host Start input; Windows game execution remains pending |
| Opening cinematic and broader interface translation | Both original-code hosts build with every method from 468 long tables registered. Linux renders moving opening footage and reaches `MSSN1040.DAT` after actual Start input. Color fidelity and complete playback remain unverified |
| Data loading after the cinematic exit | The Linux v54 host reads `MSSN1040.DAT`, with its complete sector matching EE RAM. Supplied `TITLELOGO.DAT` then passes its read and is retained in memory with 64 bytes changed during execution; `ST_RES.BIN` then loads with an exact 8 KiB sector match in EE RAM. The supplied stage group passes the `TALK_ST_RES.BIN` stop; the entire 114,688-byte `ST_RES.DAT` sector range matches EE RAM. Title rendering and original-game Windows execution remain unverified |
| Stage-resource interface translation | Linux and Windows x64 hosts build with all five verified methods registered; 21 altered-catalog checks and a supported repeat pass. Eight Linux host checks pass. Linux passes the observed method and supplied `CSE_TITLE.DAT`. Its first 51,200-byte `TITLE.ADX` read matches EE RAM. Supplied `TALK_TITLE.BIN` now allows the original Start prompt and main menu to render readable text. Native audio playback and original-game Windows execution remain unverified |
| New Game menu interfaces | Linux and Windows x64 hosts build with all 27 methods from 17 verified tables registered; 28 altered-word checks and a supported repeat pass. Eight Linux host checks pass. Start opens the original main menu and Cross selects New Game. Linux passes the callback and renders the original Chapter 1 heading after loading `CHAPTER1.DAT`. It also reads `MSSN4154.DAT`, whose complete sector matches EE RAM. The full Chapter 1 scene-data directory is now supplied; Linux passes the first descriptor stop and next requests the separate Chapter 1 movie. Image graphics and gameplay remain unverified |
| Game boot, rendering, sound, input and gameplay | Pending |

## Download the Windows diagnostic

Successful Windows jobs in the [Development tools workflow](https://github.com/TatsunaKyo/YakuzaRecomp/actions/workflows/checks.yml) publish `windows-iop-diagnostic-x64`. Open a completed run and download that artifact. The ZIP contains a Release console diagnostic, instructions, licenses and a `build-info.json` with the exact source commit and executable checksum. The package uses the static MSVC runtime and needs no compiler, Python, Linux or WSL to run.

Supply your own extracted `IRX.DAT` when testing. The package contains no original assets or translated game code. Its result checks Windows driver startup; full original-game Windows execution remains pending.

## Running the Windows diagnostic

The diagnostic is a development tool, not the game. It reads IRX.DAT without changing it and runs the original drivers in a minimal IOP host. It does not provide audio output, a real controller or memory-card behavior.

Unzip the diagnostic package, open PowerShell in that folder, and run:

```powershell
.\yakuza_iop_probe.exe "D:\Yakuza PAL\IRX.DAT" > probe.txt 2>&1
```

The minimal Linux diagnostic baseline ends with nine loaded modules, 15 threads and eight RPC servers. Start results 0 and 2 both represent resident modules. A driver initialization message about SIF not being initialized is present in this minimal host. Separately, continued original-game execution in the full Linux host loads all nine modules through the original EE-to-IOP DMA and module-start path; this does not verify every SIF service.

The private Windows full-game host cross-builds with FFmpeg disabled; the Linux host enables it for the runtime's other media paths. Native IPU MPEG block decoding and RGB32 conversion use the same implementation on both targets and do not require FFmpeg. Original movie playback remains unverified on either platform, and Windows execution with the original game data remains pending.

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
