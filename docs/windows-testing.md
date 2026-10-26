# Windows target and validation

## Experimental native Windows test

Current native Windows tests are shared with the maintainer through unpublished draft releases. Sign in with the repository account and use the private release link supplied for that test; download its ZIP under **Assets**. Extract each new test into a separate folder. Private test links and binaries are kept out of this repository.

The [older public baseline](https://github.com/TatsunaKyo/YakuzaRecomp/releases/tag/windows-pal-test-20261025) predates the stack and GIF corrections described below.

Extract every file, double-click `Run-Yakuza.cmd` and select the folder containing your own extracted European/PAL disc files (`SLES_541.71`). Keep the CVM archives intact. Python, a compiler, Linux/WSL and a PS2 BIOS are not required to run this test.

The selected disc folder must contain all 14 root files: `SYSTEM.CNF`, `SLES_541.71`, `MAIN.BIN`, `IRX.DAT`, `IOPRP300.IMG`, `PAL_NTSC.DAT`, `OGRE.CVM`, `OGRE2.CVM`, `OGRE3.CVM`, `OGRE4.CVM`, `OGREDIR.BIN`, `OGREDIR2.BIN`, `OGREDIR3.BIN` and `OGREDIR4.BIN`. A folder containing only boot files and an `.iso` or `.iso.gz` is insufficient for this native test. For a compressed image, use 7-Zip to extract `.iso.gz` to `.iso`, open the ISO and extract all its root files into one folder. Do not unpack the CVM archives. The [current launcher source](../packaging/windows-native/Run-Yakuza.cmd) checks every required filename before starting; the earlier packaged launcher checks only the two boot inputs.

This package is an experimental native host. The initial Windows 11 test reports `-1073741571` (`0xC00000FD`, Windows `STATUS_STACK_OVERFLOW`) after reading MAIN.BIN. The public baseline reserves 1 MiB of native thread stack; its unwind metadata identifies one translated constructor with a 1,018,472-byte static frame. The current source reserves 8 MiB, leaving the PS2 guest stack unchanged.

A subsequent private 8 MiB test on Windows 11 reaches the verified original MAIN entry and loads all nine IOP drivers through the original EE-to-IOP path. Its first failed disc-file lookups came from a folder containing only the two boot files and a compressed ISO. After complete extraction, `PAL_NTSC.DAT` and all eight CVM/index lookups succeed, including the archive larger than 2 GiB. The window still changes from black to purple and back to black. After approximately two minutes, the player closes it; the final code 1 follows that deliberate close, with the original loader polling an archive-read status. This does not establish a deadlock or correct rendering. Translated code is compiled before packaging.

The original Windows comparison used unoptimized runtime components, while the internal Linux build optimized those components. `YAKUZA_OPTIMIZE_BOOT_DEVICES` now defaults to ON for GCC/Clang boot hosts and applies `-O2` to the runtime, IOP, IPU and scratchpad DMA libraries. It retains the selected configuration for translated game code and leaves MSVC's configuration settings in control of that compiler. This makes the MinGW comparison consistent with the existing Linux runtime setting; improved Windows behavior still requires testing. The current launcher also records start/end wall-clock times.

The runtime-optimized Windows retest still shows black with purple flashing. Its stopped state is in the original PAL/NTSC selection loop, with the complete original `PAL_NTSC.DAT` present in RAM. A Linux run without early confirm input produces exactly the same 4 MiB of VRAM: the display buffer and its sampled full-screen texture are black. Earlier automated confirmation skipped this initial screen.

Tracing shows IMAGE headers and their pixels arriving in separate PATH3 DMA submissions. The stateless decoder discarded incomplete headers and then interpreted raw pixels as GIF commands, losing palettes and textures. The arbiter now retains partial PATH3 tags and payloads, preserves order within each path, and lets other paths proceed subject to DIRECTHL's IMAGE ordering. Native shortcuts remain blocked while a partial packet is queued. No runtime header/class layout, original instructions or DMA-completion behavior changes. An original-free test fails before the correction and passes afterward, covering all 111 byte splits of a setup/image stream, single-byte delivery, opaque pixel content, interleaved paths and DIRECTHL ordering. The original PAL/NTSC selector now renders on Linux with no confirm input.

The corrected private GIF test on Windows 11 now starts visibly, according to the maintainer. Severe slowness, poor responsiveness, artifacts and purple flashes remain. Its log verifies MAIN, GAME, nine IOP drivers and all ten PAL/IRX/CVM/index searches; it ends at controller samples without a final runtime status. The supplied exit code is 1, which alone does not establish a crash or a deliberate close. This report confirms a startup improvement, not playable performance or correct graphics.

Linux observation finds host presentation waiting up to about 100 ms on shared GS work, including a second wait solely to record diagnostic history. The host now tries the producer/backend-lifetime locks without waiting, retains the completed frame when busy and skips contended presentation-history entries. Producer rendering and device completion still follow their normal paths. An original-free concurrency regression fails before this change and passes afterward: a held producer or diagnostic snapshot cannot stall frame reuse, a ready frame does not wait for history, and new frames resume after the held work completes. This targets the window's event loop; game speed and Windows responsiveness still need measurement.

Linux testing reaches title/chapter artwork and textured scenes, with known movie artifacts, slow execution and a later untranslated call. Interactive gameplay, sound and saves remain unverified. The package contains compiled translated code and no original disc data.

The launcher writes `native-test.log` and prints the exit code. Escape or closing the window deliberately stops the probe and may return code 1; inspect the last log lines. The public ZIP was downloaded after publication and its SHA-256 matched `0c112c8ee7e2bd939dfb79503509516b44676b57f15a2747f7e704cd8949f1ad`.


The intended game target is Windows 10/11 x64. Linux is an internal development platform. A Linux test pass is never reported as a Windows runtime test.

Current evidence:

| Check | Result |
| --- | --- |
| Native Linux build and 65 Python tests | Passed |
| Overlay loader swapping, bounds and BSS tests on Linux | Passed |
| Original 11 overlays loaded into RAM; three translated routines on Linux | 768 cases passed; hardware/constructors/gameplay untested |
| Four upstream IOP test programs on Linux | Passed |
| Original PAL IRX.DAT in the Linux diagnostic runtime | Nine modules resident; eight RPC servers, 15 threads |
| LLVM-MinGW cross-build of the diagnostic for Windows x64 | Passed |
| LLVM-MinGW cross-build of overlay tests and translated routine probe | Passed; execution pending |
| Windows PE inspection | x86-64 console executable; only Windows system/UCRT DLL imports |
| Original game execution on actual Windows | Private GIF-corrected host reaches verified MAIN/GAME and nine original IOP drivers with all required disc lookups succeeding. Maintainer confirms visible startup, with severe slowness, poor responsiveness, artifacts and purple flashes. Gameplay, sound and saves remain unverified |
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
| Verified VU0 clipping arithmetic and flags | Golden tests pass on Linux and Windows/MSVC CI ([run](https://github.com/TatsunaKyo/YakuzaRecomp/actions/runs/40146509535)); the original-code Windows host cross-builds. Linux now restores title and chapter artwork and visibly renders textured 3D buildings; broader gameplay remains unverified |
| Game boot, rendering, sound, input and gameplay | Pending |

## Download the Windows diagnostic

The first packaged diagnostic passed Windows/MSVC CI and is available in [run 40123110535](https://github.com/TatsunaKyo/YakuzaRecomp/actions/runs/40123110535) under **Artifacts → windows-iop-diagnostic-x64**. This run checks the packaged executable and its system DLL imports. The player’s Windows 11 report reaches all nine resident modules, 15 threads and eight RPC servers, followed by an extra-path error for `"0"`. A clean final exit-code rerun remains pending.

Successful Windows jobs in the [Development tools workflow](https://github.com/TatsunaKyo/YakuzaRecomp/actions/workflows/checks.yml) publish `windows-iop-diagnostic-x64`. Open a completed run and download that artifact. The ZIP contains a Release console diagnostic, instructions, licenses and a `build-info.json` with the exact source commit and executable checksum. The package uses the static MSVC runtime and needs no compiler, Python, Linux or WSL to run.

Supply your own extracted `IRX.DAT` when testing. The package contains no original assets or translated game code. Its result checks Windows driver startup; full original-game Windows execution remains pending.

## Running the Windows diagnostic

The diagnostic is a development tool, not the game. It reads IRX.DAT without changing it and runs the original drivers in a minimal IOP host. It does not provide audio output, a real controller or memory-card behavior.

Unzip the diagnostic package, open PowerShell in that folder, and run:

```powershell
.\yakuza_iop_probe.exe "D:\Yakuza PAL\IRX.DAT" > probe.txt 2>&1
$LASTEXITCODE
```

Run `$LASTEXITCODE` on its own line; the probe interprets every positional argument as an input file. Windows PowerShell may wrap ordinary stderr log messages as `NativeCommandError` when redirecting output. The final program exit code and module results establish whether startup succeeded.

The minimal Linux diagnostic baseline ends with nine loaded modules, 15 threads and eight RPC servers. Start results 0 and 2 both represent resident modules. A driver initialization message about SIF not being initialized is present in this minimal host. Separately, continued original-game execution in the full Linux host loads all nine modules through the original EE-to-IOP DMA and module-start path; this does not verify every SIF service.

The private Windows full-game host cross-builds with FFmpeg disabled; the Linux host enables it for the runtime's other media paths. Native IPU MPEG block decoding and RGB32 conversion use the same implementation on both targets and do not require FFmpeg. Linux original-game playback reaches the Chapter 1 caption, with known visual corruption still under investigation. Windows execution with the original game data remains pending.

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
