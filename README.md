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
- **IPU references, MPEG tables and integer IDCT:** [PCSX2](https://github.com/PCSX2/pcsx2), its development team and the credited libmpeg2 authors.
- **Development tools:** [Ghidra](https://github.com/NationalSecurityAgency/ghidra), [Emotion Engine Reloaded](https://github.com/chaoticgd/ghidra-emotionengine-reloaded) by chaoticgd and contributors, and [LLVM-MinGW](https://github.com/mstorsjo/llvm-mingw) by Martin Storsjö and contributors.

Upstream copyright notices and licenses are retained. See [third-party notices](THIRD_PARTY_NOTICES.md) and [COPYING](COPYING).

## What happens next

The original loader now reads MAIN.BIN and reaches its entry point in the Linux native runtime. Continued execution initializes its nine IOP drivers, reads the supplied boot assets, loads GAME.BIN and enters that module's original initialization. The host verifies both MAIN code and the complete GAME image in memory. The SEGA logo and memory-card message data load. After additional method translations and a VIF upload correction, the original memory-card dialog is readable. Host input advances beyond it and completes the requested mission-data read. The opening-movie worker reads the supplied chunks. Native IPU bit handling, MPEG symbol/block decoding and corrected 64-bit waits let the original movie code pass its macroblock output transfers into the PS2 scratchpad. Native RGB32 color conversion and scratchpad DMA chains now reconstruct frames from the supplied opening movie. One recovered frame matches an independent decode within a one-level rounding difference. Correct complete playback and on-screen presentation remain unverified. The original “Press START button” prompt and New Game / Load Game / Options menu now render readable text. Start opens the menu; selecting New Game reaches further original code. The title logo and background are absent in the current capture, and gameplay remains unverified.

1. **Continue game initialization.** Trace execution beyond GAME's initialization, fixing missing indirect targets and runtime behavior as they are encountered. Integrate other gameplay and minigame modules when execution loads them.
2. **Trace required data.** Record failed file requests and prepare original assets as they become necessary.
3. **Validate Windows execution.** Run the diagnostic and boot builds on Windows, checking crashes, dependency loading and paths. Cross-compilation alone does not complete this milestone.
4. **Bring up the game.** Work through graphics and VU behavior, audio, controls, memory-card saves and gameplay, validating each feature with the original PAL data.

The complete original PAL disc is now available in private development storage. Its gzip stream passes integrity verification, all 14 root files are verified, and every byte of the 42 earlier archive excerpts matches the complete archives. Existing supplied originals and excerpts are preserved. The native host can now read complete OGRE.CVM, OGRE2.CVM and OGRE3.CVM files, removing the need for another upload at each new asset read. Data availability does not establish execution coverage. Selected reconstructed movie frames match an independent decoder within a one-level sample difference. Moving opening footage renders in the Linux host, and actual Start input exercises its exit. Displayed colors and complete playback remain under investigation.

After the cinematic, native execution loads the supplied mission, title, stage and CSE resources. The first 51,200-byte `TITLE.ADX` read matches game memory. The supplied title-text file now allows the original prompt and main menu to appear. Selecting New Game exposed another original method-table family, which is now verified and translated. The Linux run passes that call, loads supplied `CHAPTER1.DAT` and displays the original Chapter 1 heading, “October 1st, 1995 — Fate of a Traitor.” The next `MSSN4154.DAT` mission read now completes, with all 8,192 sector bytes matching game memory. The complete Chapter 1 scene-data directory and its separate movie, `AUTH_CHAPTER01_001.SFD`, are now supplied. The Linux host renders moving Kamurocho footage from that movie. An independent full video decode passes, confirming the supplied file is complete. After correcting native wakeup acknowledgements, a clean run advances through the closing fade without skip input and requests the next scene's caption data. That caption directory and all seven caption movies are now supplied. Native execution renders the animated date from `CAPTION01.SFD`, finishes it without skip input and requests the Dojima stage archive, `ST_DOJIMA1.ARC`. All 1,021,952 bytes of the caption movie match their copy in game memory. A color cast, a corrupted strip along the bottom and an intermittent repeated-frame stall remain under investigation. Correct complete playback, native audio output, complete title presentation and gameplay remain unverified.

The native IOP now defers sound-DMA, timer and disc-completion callbacks while global interrupts are disabled, and preserves a masked critical section across host instruction-budget boundaries. Direct RPC dispatch waits for that section to finish. Imported calls also consume pending MIPS loads before reading their arguments. Synthetic regressions check both DMA cores, ordinary and nested restoration, delay-slot arguments, exactly-once notification delivery, RPC ordering and priority scheduling after restoration. Explicit guest yields still work. The effect on movie stability and native audio remains under test.

Three packed-integer lane permutations used by sprite rendering are also corrected in the private runtime headers. A regression reproduces the observed reduction of the blue channel before the fix and checks correct channel ordering after it. Both full hosts build, and Windows/MSVC and Linux CI passes. Selected opening footage now renders without the earlier yellow cast. The corrected clean run finishes the Chapter 1 movie and caption without extra skip input and passes the effects load. The corrupted bottom strip remains unresolved.

A later native run loads both Dojima resources: the complete 922,616-byte stage archive and 7,508-byte English companion match game memory exactly. The next original callback exposed another family of 16 method tables. Its 65 methods are now translated, with all earlier callable entries retained. Stage presentation and gameplay remain unverified.

An earlier clean native run finishes the Chapter 1 movie and animated caption without skip input, retains the complete Dojima stage archive and passes the shared enemy-data boundary. Bundle 34 supplies all four shared enemy-initialization files, preserving every previous excerpt record. All 201,968 bytes of `ENECOMMON.DAT` match game memory. The next missing read was `/MEDIA/EFFECT/EFFECT_1ST.DAT`. Bundle 35 supplies all eight files in its effects directory, verified against the original index, and preserves all earlier records. A clean run passes that boundary and retains the complete 6,480-byte `ENVIRONMENT.DAT` file in game memory. Bundle 36 supplies the complete `/MEDIA/ADVMISC/ADVMISC00.DAT`, preserving every earlier record. A continued diagnostic run finishes the movie and caption and retains all 10,064 bytes of that file in game memory. Bundle 37 supplies all 712 particle files, and a further diagnostic run passes the former `PTCL_AUTH.DAT` read. Its next missing file was `/MEDIA3/ENEMY/E434/E43400.DAT`, which is now available in the verified complete OGRE3.CVM. A separate clean run reproduced the intermittent original CRI audio-driver invalid-handle error; the diagnostic run did not reproduce it, so the cause remains under investigation. A subsequent diagnostic run with the recovered graphics methods observes 604 entries to the former missing graphics call and repeated packed-interpolation calls. The post-movie scene remains nearly blank; the run was stopped explicitly for inspection. These counters establish observed dispatch, not completed rendering. Movie stability, stage rendering and gameplay still need work.

A [Windows collection tool](docs/disc-ranges.md) remains available for collecting exact original ranges from an extracted disc folder, `.iso` or `.iso.gz` into a private ZIP. A [bulk transfer tool](docs/bulk-data.md) can compress whole original archives and split them into upload-sized ZIP volumes in one ISO scan. Neither requires a full decompressed ISO copy. Development now uses the verified complete archives supplied through a private download link. Original game data and the download link remain outside this repository.

The supplied `PAL_NTSC.DAT` now loads through the original disc-read path. Native vertical-blank and recursive-dispatch fixes address observed stack corruption. A first-port controller adapter passes host keyboard input into the original PAL selection code; an X key press is observed as Cross. Execution then reaches filesystem and archive initialization. A priority-syscall correction lets the original I/O workers run, and supplemental translation retains previously identified callback entries. A VIF transfer-boundary correction removes control words from image uploads. The captured memory-card dialog is now readable, and its entire 32 KiB font texture and 64-byte palette match their original EE upload sources byte for byte. Other graphics remain unverified.

A native replay with the complete archives finishes the Chapter 1 movie and caption and advances beyond the former enemy-data stop. It next reaches an untranslated packed interpolation callback. The original selector and all eight related wrappers are now fingerprinted and translated; four previously unrecognized callable entries are added while all earlier translations are retained. Another replay reaches an original graphics-interface call. Its complete three-method table is now verified, adding two more callable entries. Altered original code and tables are rejected before classification changes. One replay reproduces the intermittent audio-driver invalid-handle error; another does not. That error remains unresolved. Execution with the new translations is being validated separately; this is not a playable-stage milestone.

Private incremental builds can now retain the physical paths and compatible headers of verified unchanged translations. For the graphics callback update, Linux and Windows compiled only the two new routines and their registration, reusing all 402 earlier translation files. Changes to the shared runtime layout still require rebuilding dependent game code.

There is no release date yet. Completing translation is one part of the work; runtime behavior and game compatibility still need substantial development.

## Current evidence

- Resident and MAIN overlay code analyzed with the PS2 R5900 Ghidra extension.
- Eleven original method-table catalogs verified by SHA-256: 298 distinct tables containing 892 methods. Analysis identifies previously missing callback entries while preserving original instruction bytes. This does not establish execution coverage for every method.
- A broader scan verifies 468 long interface tables containing 3,460 distinct method pointers, plus fingerprints of 60 previously unregistered entries. These tables overlap earlier catalogs. Supplemental translation registers every method pointer and retains earlier callable addresses.
- Movie driver analysis verifies three original driver variants and all 98 method slots in their seven interfaces. Supplemental translation registers every verified method pointer and retains prior callable entries; altered descriptor and method data are rejected before analysis changes.
- A static generation probe reports zero unhandled-instruction errors, with unresolved control-flow warnings still remaining.
- The resident/MAIN translation compiles and links with the full desktop runtime for Linux x86-64 and Windows x64. A newly discovered resident constructor is translated separately, with the original instruction bytes verified.
- All nine original driver modules from the supplied PAL IRX.DAT initialized in the minimal IOP probe, creating eight RPC servers. This does not verify audio, controller or memory-card behavior.
- Continued MAIN execution also loads and starts all nine drivers through the original game's DMA/module-loading path in the full runtime. After native memory-layout and vertical-blank corrections, the graphics allocation succeeds, PAL_NTSC.DAT loads and execution continues through the frame loop. The memory-card dialog, title prompt and main menu render readable text. The title logo and background are absent in the current capture; gameplay rendering remains unverified.
- All four archive indexes parsed: 18,685 files. The supplied OGRE4.CVM yielded all 11 gameplay/minigame overlays; their sizes match the original ELF's overlay slots.
- All 11 overlays analyzed separately: 10,348 decoded code ranges, 865,866 instructions, zero translation errors and 7,460 unresolved control-flow warnings. This does not establish complete code coverage.
- The full runtime compiles GAME's 1,750 decoded ranges and activates its 94,618 callable entries at the original resident initialization boundary. It verifies the complete 704,896-byte image already loaded by the game, clears stale dispatch entries and retains original BSS/constructor behavior. Original execution passes the observed constructor callback and reads the SEGA logo data. The other ten modules are not yet included in this full host.
- A Linux RAM-only probe loaded all 11 overlays and passed 768 cases across three small translated GAME/HEALTH/UFO routines. Constructors, hardware and full gameplay were not executed by that probe.
- Linux checks pass: 57 Python tests, overlay swapping/bounds checks, controller packet conversion, bounded archive-range reads and four upstream IOP test programs. Synthetic ISO/gzip tests check exact excerpts, PAL index rejection, truncation, Unicode paths and archive sizes above 2 GiB. Supplemental translation tests verify that earlier callable entries survive later passes. Full-runtime tests cover recursive dispatch, priority return values, the thread-ID result needed for resume-then-wake, VIF image boundaries, 6,319 command-fragmentation boundaries, IRQ acknowledgement and reset, verified overlay activation and stale-entry removal. IPU tests check standard VLC symbols, known IDCT pixel values, signed residuals, interlaced block placement, split input and output DMA to main RAM and scratchpad. The default tools and synthetic full-runtime host passed Windows/MSVC and Linux CI including the VIF fragmentation and thread-resume regressions ([run](https://github.com/TatsunaKyo/YakuzaRecomp/actions/runs/40125465940)). These jobs do not run the original game.
- The full host with GAME, the synthetic runtime tests and the IOP diagnostic cross-build successfully for Windows x64 with LLVM-MinGW. Full original-game Windows execution remains pending; see [Windows validation](docs/windows-testing.md).

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
