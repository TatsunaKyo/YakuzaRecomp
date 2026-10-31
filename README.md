# YakuzaRecomp

An experimental native PC recompilation project for the original **Yakuza on PlayStation 2**, led and maintained by **[TatsunaKyo](https://github.com/TatsunaKyo)**.

The goal is to bring the original PS2 game to **Windows 10/11 x64** through static recompilation. The supported research build is the **European/PAL release, SLES-54171**. Linux is used internally for development; the eventual Windows port should not require Linux or WSL.

**Status: early development. There is no playable game build yet.** The current tools prepare original disc files, analyze game code, test runtime components and build an opt-in full-runtime boot probe. Diagnostic executables are development tools, not the game.

Current native Windows tests are shared privately with the maintainer. Severe slowness, poor responsiveness and visual artifacts remain; purple flashes appear improved. The latest reported Windows 11 shutdown is JALR `0x29c4c4` to untranslated GAME target `0x69ff50`, after passing the previously recovered `0x636660`. The original target instructions and the pointer's provenance still need verification before further translation. Earlier logs verify MAIN, GAME, all nine original IOP drivers and successful PAL/CVM/index lookups. Interactive gameplay, sound and saves remain unverified. The [older public baseline](https://github.com/TatsunaKyo/YakuzaRecomp/releases/tag/windows-pal-test-20261025) predates the stack and GIF fixes. See [Windows testing](docs/windows-testing.md) for the data layout and current limits.

The blank initial PAL/NTSC selector had a reproducible cause: the GIF runtime discarded an image header when its pixels arrived in another DMA submission. Retaining that incomplete packet restores the original selector on Linux without early confirm input; the corrected Windows test now also produces visible output. Host presentation additionally avoids waiting on busy GS producer and diagnostic locks, retaining the previous completed frame until another can be captured. This targets window responsiveness; it does not establish a game-speed improvement.

Generated code also bypassed the corrected runtime macros at 69 inline PEXEH/PROT3W sites. Private compilation copies now route those operations through the verified lane permutations, preserving the original instructions and generated inputs. An original-free test of actual recompiler output fails before this correction and passes afterward. Any improvement to the remaining visual artifacts still needs original-game testing.

The earlier audio failure reproduces on Linux: a directly dispatched RPC destroys buffers before an interrupted audio worker resumes using them. Current IOP source dispatches queued RPC callbacks in their registered server thread, using its stack, priority and waits. PCM16 AutoDMA additionally follows the 48 kHz input-consumption clock. Synthetic regressions fail before these changes and pass afterward; the existing call guard and original error paths remain enabled. The preceding Windows stability log reached missing GAME callback `0x636660` without that earlier error; this does not establish complete audio correctness.

Recovery of the earlier `0x636660` callback verifies the original class-method tables and translates 224 previously missing GAME method entries, retaining every earlier callable entry. The resulting GAME module has 95,309 callable entries. Two nearby methods pass 56 checks of their actual translations, including return/delay-slot behavior, CPU state and unchanged RAM. Both Linux and Windows hosts built for that recovery; the latest maintainer report passes that stop and reaches `0x69ff50`. This next target has not been translated or validated.

The native IOP scheduler also caches the next event deadline while no thread can run. It advances only within the requested time budget and resumes normal scheduling at due events or new work. Timer, both AutoDMA cores and later RPC wakeup checks pass. A benchmark of sleeping threads improves, but this is not a measured game frame-rate improvement. Rendering still uses the CPU GS backend, and VU/IOP interpretation remains part of the runtime.

This is an unofficial fan project, unaffiliated with SEGA. Original game files are not distributed with this repository.

## Project credits

- **Project lead and maintainer:** [TatsunaKyo](https://github.com/TatsunaKyo).
- **Original game:** SEGA and the original Yakuza development team. All original game content and trademarks belong to their respective owners.
- **Recompilation and IOP framework:** [PS2Recomp](https://github.com/ran-j/PS2Recomp) and its contributors.
- **Archive format references:** [YakuzaPythonExtractor](https://github.com/LinuxJessi/YakuzaPythonExtractor), by Jessi Ray Godsibb.
- **IPU/SPU2 references, MPEG tables and integer IDCT:** [PCSX2](https://github.com/PCSX2/pcsx2), its development team and the credited libmpeg2 authors.
- **IOP RPC queue reference:** [PS2SDK](https://github.com/ps2dev/ps2sdk) contributors.
- **Development tools:** [Ghidra](https://github.com/NationalSecurityAgency/ghidra), [Emotion Engine Reloaded](https://github.com/chaoticgd/ghidra-emotionengine-reloaded) by chaoticgd and contributors, and [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw) by Martin Storsjö and contributors.

Upstream copyright notices and licenses are retained. See [third-party notices](THIRD_PARTY_NOTICES.md) and [COPYING](COPYING).

## Current progress and next steps

The native Linux host boots the original PAL executable, verifies MAIN and GAME in memory, and starts all nine original IOP drivers. The memory-card dialog, title prompt and main menu respond to host input. The title logo and dragon background, Chapter 1 artwork and textured 3D scenes now render. The opening movie and animated caption complete without additional skip input, with known visual corruption still under investigation.

An extended replay continues through changing scenes, including buildings and a textured ring. It records no missing translation or CRI error before an explicit diagnostic stop. A subsequent longer run reaches another untranslated call; further progression remains under development. Dark final frames alternate with brighter intermediate frames; a final screenshot alone does not establish a rendering stall. Execution is slow, and correct rendering, interactive gameplay, sound and saves remain unverified.

The complete original PAL disc was previously verified privately: all 14 root files, every byte of the 42 earlier archive excerpts and all 18,685 indexed file extents. The resumed executor has recovered the public source and confirmed the retained private Windows test package, but has not recovered the original disc, Ghidra projects or generated game sources. Original-code investigation and a new game build remain blocked on those private inputs. Original disc data, generated original-game code, private test binaries and download links stay outside this repository.

The next milestones are:

1. **Reach and validate gameplay.** Follow the original scene sequence and resolve newly observed runtime or translation failures.
2. **Improve rendering and speed.** Trace the remaining movie artifacts and measure expensive execution paths.
3. **Continue Windows validation.** Compare window responsiveness, rendering and controls with the Linux host after the confirmed startup improvement.
4. **Validate controls, sound and saves.** Check these features with the original PAL data as gameplay becomes accessible.

There is no release date yet. See [boot development](docs/boot-probe.md), [Windows validation](docs/windows-testing.md) and the [disc collection tools](docs/disc-ranges.md) for the research workflow.

## Current evidence

- Resident and MAIN overlay code analyzed with the PS2 R5900 Ghidra extension.
- Eleven original method-table catalogs verified by SHA-256: 298 distinct tables containing 892 methods. Analysis identifies previously missing callback entries while preserving original instruction bytes. This does not establish execution coverage for every method.
- A broader scan verifies 468 long interface tables containing 3,460 distinct method pointers, plus fingerprints of 60 previously unregistered entries. These tables overlap earlier catalogs. Supplemental translation registers every method pointer and retains earlier callable addresses.
- Movie driver analysis verifies three original driver variants and all 98 method slots in their seven interfaces. Supplemental translation registers every verified method pointer and retains prior callable entries; altered descriptor and method data are rejected before analysis changes.
- A static generation probe reports zero unhandled-instruction errors, with unresolved control-flow warnings still remaining.
- The resident/MAIN translation compiles and links with the full desktop runtime for Linux x86-64 and Windows x64. A newly discovered resident constructor is translated separately, with the original instruction bytes verified.
- All nine original driver modules from the supplied PAL IRX.DAT initialized in the minimal IOP probe, creating eight RPC servers. This does not verify audio, controller or memory-card behavior.
- Continued MAIN execution also loads and starts all nine drivers through the original game's DMA/module-loading path in the full runtime. After native memory-layout and vertical-blank corrections, the graphics allocation succeeds, PAL_NTSC.DAT loads and execution continues through the frame loop. The memory-card dialog, title prompt and main menu render readable text. The title logo/background, Chapter 1 artwork and textured 3D scenes now render; interactive gameplay remains unverified.
- All four archive indexes parsed: 18,685 files. The supplied OGRE4.CVM yielded all 11 gameplay/minigame overlays; their sizes match the original ELF's overlay slots.
- All 11 overlays analyzed separately: 10,348 decoded code ranges, 865,866 instructions, zero translation errors and 7,460 unresolved control-flow warnings. This does not establish complete code coverage.
- The full runtime compiles GAME's 1,983 decoded ranges and activates its 95,309 callable entries at the original resident initialization boundary. All earlier 94,618 entries and 1,750 translation sources are retained. It verifies the complete 704,896-byte image already loaded by the game, clears stale dispatch entries and retains original BSS/constructor behavior. Original execution passes the observed constructor callback and reads the SEGA logo data. The other ten modules are not yet included in this full host.
- A Linux RAM-only probe loaded all 11 overlays and passed 768 cases across three small translated GAME/HEALTH/UFO routines. Constructors, hardware and full gameplay were not executed by that probe.
- Linux checks pass: 65 Python tests, overlay swapping/bounds checks, controller packet conversion, bounded archive-range reads and four upstream IOP test programs. Synthetic ISO/gzip tests check exact excerpts, PAL index rejection, truncation, Unicode paths and archive sizes above 2 GiB. Supplemental translation tests verify that earlier callable entries survive later passes. Full-runtime tests cover recursive dispatch, priority return values, the thread-ID result needed for resume-then-wake, VIF image boundaries, 6,319 command-fragmentation boundaries, IRQ acknowledgement and reset, verified overlay activation and stale-entry removal. IPU tests check standard VLC symbols, known IDCT pixel values, signed residuals, interlaced block placement, split input and output DMA to main RAM and scratchpad. The default tools and synthetic full-runtime host passed Windows/MSVC and Linux CI including VIF barriers/live register reads, VBlank latches, thread initialization/resume, vector flags, Windows stack handling and the complete Linux display handshake ([run](https://github.com/TatsunaKyo/YakuzaRecomp/actions/runs/40205486144)). These jobs do not run the original game.
- The full host with GAME, the synthetic runtime tests and the IOP diagnostic cross-build successfully for Windows x64 with LLVM-MinGW. Windows testing reaches movies and the main menu with unresolved speed, rendering and stability defects; see [Windows validation](docs/windows-testing.md).

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

PS2Recomp is pinned to eb8688b2fd191129f103a39543002c005b33409c. Its checkout stays unchanged; the opt-in boot target applies documented runtime adaptations to private build copies. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for upstream sources and licenses.

## License

The project tooling is provided under **GPL-3.0-or-later**, with upstream components retaining their own notices and applicable licenses. See [COPYING](COPYING) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This license does not grant rights to SEGA's original game code, assets or trademarks.
