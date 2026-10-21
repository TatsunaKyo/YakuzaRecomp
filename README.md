# YakuzaRecomp

An experimental native PC recompilation project for the original **Yakuza on PlayStation 2**, led and maintained by **[TatsunaKyo](https://github.com/TatsunaKyo)**.

The goal is to bring the original PS2 game to **Windows 10/11 x64** through static recompilation. The supported research build is the **European/PAL release, SLES-54171**. Linux is used internally for development; the eventual Windows port should not require Linux or WSL.

**Status: early development. There is no playable game build yet.** The current tools prepare original disc files, analyze game code, test runtime components and build an opt-in full-runtime boot probe. Diagnostic executables are development tools, not the game.

This is an unofficial fan project, unaffiliated with SEGA. Original game files are not distributed with this repository.

## Project credits

- **Project lead and maintainer:** [TatsunaKyo](https://github.com/TatsunaKyo).
- **Original game:** SEGA and the original Yakuza development team. All original game content and trademarks belong to their respective owners.
- **Recompilation and IOP framework:** [PS2Recomp](https://github.com/ran-j/PS2Recomp) and its contributors.
- **Archive format references:** [YakuzaPythonExtractor](https://github.com/LinuxJessi/YakuzaPythonExtractor), by Jessi Ray Godsibb.
- **Development tools:** [Ghidra](https://github.com/NationalSecurityAgency/ghidra), [Emotion Engine Reloaded](https://github.com/chaoticgd/ghidra-emotionengine-reloaded) by chaoticgd and contributors, and [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw) by Martin Storsjö and contributors.

Upstream copyright notices and licenses are retained. See [third-party notices](THIRD_PARTY_NOTICES.md) and [COPYING](COPYING).

## What happens next

The original loader now reads MAIN.BIN and reaches its entry point in the Linux native runtime. The boot probe verifies the original MAIN code in memory before recording that milestone. Continued execution enters MAIN initialization and exposes the next unsupported SDK services. There is no working title screen yet.

1. **Initialize game services.** Continue through MAIN's disc and IOP module initialization, fixing the failures revealed by execution. Connect gameplay overlay loading to the active function table and constructor calls.
2. **Trace required data.** Record failed file requests and prepare original assets as they become necessary.
3. **Validate Windows execution.** Run the diagnostic and boot builds on Windows, checking crashes, dependency loading and paths. Cross-compilation alone does not complete this milestone.
4. **Bring up the game.** Work through graphics and VU behavior, audio, controls, memory-card saves and gameplay, validating each feature with the original PAL data.

The supplied private boot-data bundles provide original headers from OGRE.CVM, OGRE2.CVM and OGRE3.CVM, plus ranges covering `00000_CMN.DAT`, `SCENARIOSTATEDATA.BIN` and `PLAYERPOS.BIN`. The native host mounts those partial archives and completes all three reads. The next traced request needs a 4 KiB range covering `TALK_NOWLOADING.BIN`. A [Windows collection tool](docs/disc-ranges.md) reads an extracted disc folder, `.iso` or `.iso.gz` and copies exact original ranges into a private ZIP. Compressed images do not require a full decompressed copy. The complete three archives remain absent.

The supplied `PAL_NTSC.DAT` now loads through the original disc-read path. Native vertical-blank and recursive-dispatch fixes address observed stack corruption. A first-port controller adapter passes host keyboard input into the original PAL selection code; an X key press is observed as Cross. Execution then reaches filesystem and archive initialization. A priority-syscall correction lets the original I/O workers run, and supplemental translation retains previously identified callback entries. Captured output is still blank/incorrect.

There is no release date yet. Completing translation is one part of the work; runtime behavior and game compatibility still need substantial development.

## Current evidence

- Resident and MAIN overlay code analyzed with the PS2 R5900 Ghidra extension.
- A static generation probe reports zero unhandled-instruction errors, with unresolved control-flow warnings still remaining.
- The resident/MAIN translation compiles and links with the full desktop runtime for Linux x86-64 and Windows x64. A newly discovered resident constructor is translated separately, with the original instruction bytes verified.
- All nine original driver modules from the supplied PAL IRX.DAT initialized in the minimal IOP probe, creating eight RPC servers. This does not verify audio, controller or memory-card behavior.
- Continued MAIN execution also loads and starts all nine drivers through the original game's DMA/module-loading path in the full runtime. After native memory-layout and vertical-blank corrections, the graphics allocation succeeds, PAL_NTSC.DAT loads and execution continues through the frame loop. Correct rendering remains unverified.
- All four archive indexes parsed: 18,685 files. The supplied OGRE4.CVM yielded all 11 gameplay/minigame overlays; their sizes match the original ELF's overlay slots.
- All 11 overlays analyzed separately: 10,348 decoded code ranges, 865,866 instructions, zero translation errors and 7,460 unresolved control-flow warnings. This does not establish complete code coverage.
- A native overlay loader copies original payloads, clears BSS and replaces the prior overlay's dispatch table. Its connection to the full game runtime remains to be implemented.
- A Linux RAM-only probe loaded all 11 overlays and passed 768 cases across three small translated GAME/HEALTH/UFO routines. Constructors, hardware and full gameplay were not executed by that probe.
- Linux checks pass: 40 Python tests, overlay swapping/bounds checks, controller packet conversion, bounded archive-range reads and four upstream IOP test programs. Synthetic ISO/gzip tests check exact excerpts, PAL index rejection, truncation, Unicode paths and archive sizes above 2 GiB. Supplemental translation tests verify that earlier callable entries survive later passes. Synthetic full-runtime tests reproduce recursive-dispatch and priority-return failures before their fixes and pass afterward. The published default tools and a synthetic full-runtime host also passed Windows/MSVC CI ([run](https://github.com/TatsunaKyo/YakuzaRecomp/actions/runs/39579299033)). These jobs do not run the original game.
- A Windows x64 diagnostic executable cross-builds successfully with LLVM-MinGW. Actual Windows execution remains pending; see [Windows validation](docs/windows-testing.md).

The Linux boot probe passes the deliberate MAIN-entry checkpoint. Continued execution prints the original initialization messages, reads IRX.DAT and starts its drivers. PAL-specific SDK bindings cover the observed kernel, SIF, file, CD and IOP heap interfaces. Further IOP integration, rendering and gameplay remain in development. See [boot development](docs/boot-probe.md).

The overlay loader and translated routine probe also cross-build for Windows x64. See [overlay research](docs/overlays.md) for the private analysis workflow and its limits.

No original game files or generated game code are included. Supply your own disc files outside this checkout.

## Preparation on Windows

With Python 3.10 or newer installed, open PowerShell in this repository:

```powershell
py -3 tools/prepare_game.py inspect --disc-dir "D:\Yakuza PAL" --out-dir "$env:LOCALAPPDATA\YakuzaRecomp\research"
```

The disc folder needs SYSTEM.CNF, SLES_541.71, MAIN.BIN, IRX.DAT, IOPRP300.IMG and the four OGREDIR indexes. The tool checks the supported executable hashes, creates a manifest and extracts the IOP images. It reads the source files without modifying them and refuses to overwrite different existing outputs.

With OGRE4.CVM in the same disc folder, extract the code overlays with:

```powershell
py -3 tools/prepare_game.py extract-overlays --disc-dir "D:\Yakuza PAL" --out-dir "$env:LOCALAPPDATA\YakuzaRecomp\overlays"
```

Spaces and Unicode in host paths are supported. Some original archive names end in dots, so the index keeps the original names; the overlay extractor validates names before writing them to Windows. A future game data reader can access archive extents directly without extracting every filename to the host filesystem.

## Native diagnostic build on Windows

Install Git, CMake 3.21+ and Visual Studio 2022 with the **Desktop development with C++** workload. From a developer PowerShell:

```powershell
cmake -S . -B out/windows -A x64
cmake --build out/windows --config Debug --parallel 2
ctest --test-dir out/windows -C Debug --output-on-failure
.\out\windows\Debug\yakuza_iop_probe.exe "D:\Yakuza PAL\IRX.DAT"
```

CMake fetches a pinned PS2Recomp revision and builds only its IOP component. The probe loads original IRX modules into a bounded diagnostic host. It supplies no rendered game, audio output, EE callbacks, disc I/O or real memory-card behavior. Module initialization success is an early compatibility check.

## Linux development

```sh
python3 -m unittest discover -s tests -v
cmake -S . -B out/linux -DCMAKE_BUILD_TYPE=Debug
cmake --build out/linux --parallel 2
ctest --test-dir out/linux --output-on-failure
out/linux/yakuza_iop_probe /path/to/IRX.DAT
```

PS2Recomp is pinned to eb8688b2fd191129f103a39543002c005b33409c. Its checkout stays unchanged; the opt-in boot target applies documented PAL memory-layout adaptations to private build copies. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for upstream sources and licenses.

## License

The project tooling is provided under **GPL-3.0-or-later**, with upstream components retaining their own notices and applicable licenses. See [COPYING](COPYING) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This license does not grant rights to SEGA's original game code, assets or trademarks.
