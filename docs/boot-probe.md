# Full-runtime boot development

The opt-in `yakuza_boot_probe` target links the verified resident/MAIN translation and optional gameplay overlays to the full PS2Recomp desktop runtime. The original loader reads MAIN.BIN and reaches `0x0022cc40`. The probe verifies the original MAIN code in memory, then deliberately stops before executing its body. With `continue` enabled, MAIN starts all nine original drivers, reads the supplied boot assets and loads GAME.BIN. Execution reads the original SEGA logo and memory-card message data. The memory-card dialog is now readable after additional method translations and a VIF upload correction. Host input advances beyond it, loads the supplied mission data and reaches the opening-movie read after a thread-resume correction. Logo, title-screen and gameplay rendering remain unverified. This executable is not a playable release.

Original disc files and generated game source remain outside the repository. The default build does not fetch graphics dependencies or compile game code. Enable this target only when private verified translations are available.

## Windows development build

With Visual Studio 2022's C++ workload, Git, Python 3.10+ and CMake installed, use a developer PowerShell:

```powershell
cmake -S . -B "$env:LOCALAPPDATA\YakuzaRecomp\boot-build" -A x64 `
  -DYAKUZA_BUILD_BOOT_PROBE=ON `
  -DYAKUZA_MAIN_GENERATED_DIR="D:\Yakuza Research\generated-pal-probe" `
  -DYAKUZA_BOOT_SUPPLEMENT_DIR="D:\Yakuza Research\boot-supplement-v42\generated" `
  -DYAKUZA_BOOT_OVERLAY_DIRS="D:\Yakuza Research\overlay-analysis-boot-v3\game" `
  -DPS2X_ENABLE_FFMPEG=OFF
cmake --build "$env:LOCALAPPDATA\YakuzaRecomp\boot-build" --config Debug --parallel 2 --target yakuza_boot_probe
& "$env:LOCALAPPDATA\YakuzaRecomp\boot-build\Debug\yakuza_boot_probe.exe" "D:\Yakuza PAL" 15 "$env:LOCALAPPDATA\YakuzaRecomp\boot-state"
```

The generated directories must contain the real verified resident/MAIN `.cpp` files, registration and headers, plus the resident supplement. Each `YAKUZA_BOOT_OVERLAY_DIRS` entry points to a complete verified analysis directory containing original layout metadata, ELF view, decoded map, saved verification report and `generated` sources. The synthetic CI fixture cannot run the game. Put the build outside this checkout because its private registration contains generated game code. The diagnostic validates the supported SLES_541.71 and MAIN.BIN fingerprints before starting the runtime, and the Python runner additionally checks their SHA-256 hashes plus SYSTEM.CNF. On entry to MAIN it checks the loaded header and the fingerprint of all 3,026,720 primary code bytes.

Append `continue` after the state folder to execute MAIN's body. A continued run has no success completion condition yet and returns nonzero when stopped. Reaching MAIN and completing a playable boot are separate results.

The initial Windows cross-build disables FFmpeg video decoding explicitly. This limits media behavior and is not a completed video implementation. The native Linux development build enables system FFmpeg. Full gameplay graphics, audio and controls remain unverified.

## Internal Linux boot attempt

The cloud's desktop SDK is installed under `/workspace/.cache/yakuza-onboarding/desktop-sdk/root`. Debian Release signatures, the package index and every extracted package checksum are verified. No system installation is needed. The SDK provides X11/OpenGL/FFmpeg development files and Xvfb; the public source does not depend on this particular cloud layout.

```sh
source /workspace/.cache/yakuza-onboarding/activate.sh
export PKG_CONFIG_LIBDIR=/workspace/.cache/yakuza-onboarding/desktop-sdk/root/usr/lib/x86_64-linux-gnu/pkgconfig:/workspace/.cache/yakuza-onboarding/desktop-sdk/root/usr/share/pkgconfig
export PKG_CONFIG_SYSROOT_DIR=/workspace/.cache/yakuza-onboarding/desktop-sdk/root
cmake -S . -B /workspace/scratch/yakuza-pal/boot-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON \
  -DFETCHCONTENT_SOURCE_DIR_PS2RECOMP=/workspace/.cache/yakuza-onboarding/PS2Recomp \
  -DCMAKE_PREFIX_PATH=/workspace/.cache/yakuza-onboarding/desktop-sdk/root/usr \
  -DYAKUZA_BUILD_BOOT_PROBE=ON \
  -DYAKUZA_MAIN_GENERATED_DIR=/workspace/scratch/yakuza-pal/generated-pal-probe \
  -DYAKUZA_BOOT_SUPPLEMENT_DIR=/workspace/scratch/yakuza-pal/boot-supplement-v42/generated \
  -DYAKUZA_BOOT_OVERLAY_DIRS=/workspace/scratch/yakuza-pal/overlay-analysis-boot-v3/game
cmake --build /workspace/scratch/yakuza-pal/boot-build --target yakuza_boot_probe --parallel 2
python tools/run_boot_probe.py \
  --exe /workspace/scratch/yakuza-pal/boot-build/yakuza_boot_probe \
  --disc-dir /workspace/library-files/yakuza-pal \
  --out-dir /workspace/scratch/yakuza-pal/new-boot-attempt \
  --seconds 15 \
  --xvfb /workspace/.cache/yakuza-onboarding/desktop-sdk/root/usr/bin/Xvfb
```

Choose a fresh output directory for each run. The runner preserves the executable digest, original input hashes, exit status and trace. Available IRX.DAT, IOPRP300.IMG and PAL_NTSC.DAT hashes are also recorded, without requiring them for the earlier MAIN checkpoint. Its outer timeout can kill a stuck process if the runtime's cooperative stop fails. The temporary display is shut down afterward. The native run may report no available audio device in the cloud; this does not test sound output. Save-state paths are separate from the original disc files.

Add `--continue-main` to the Python command to continue into MAIN. This mode also records register values, display/DMA activity and IOP diagnostics at shutdown. PAL_NTSC.DAT is now supplied and its original two-part sector read completes. A host Cross press leaves the selection loop and reaches filesystem initialization, which searches for the absent OGRE.CVM, OGRE2.CVM and OGRE3.CVM. Missing second-layer probes return the normal SDK search-failure result.

The optional [private archive-range reader](disc-ranges.md) mounts original logical file sizes from supplied excerpt records, using separate virtual sector addresses. Complete original files take priority. The host checks complete byte coverage before writing guest RAM and stops on a missing range. The supplied excerpts now complete nine OGRE.CVM reads: `00000_CMN.DAT` at offset `0x6561800`, length `0x47800`; `SCENARIOSTATEDATA.BIN` at `0x2063e800`, length `0x10000`; `PLAYERPOS.BIN` at `0x6545000`, length `0x8800`; `TALK_NOWLOADING.BIN` at `0x20ca0000`, length `0x1000`; `CSE_STAY.DAT` at `0x10ce800`, length `0xa800`; `MSSN1000.DAT` at `0x31f0000`, length `0x800`; `SEGALOGO.DAT` at `0x8d1000`, length `0x51000`; `TALK_MEMCARD.BIN` at `0x207a0000`, length `0x14000`; and `MSSN1010.DAT` at `0x31f1800`, length `0x800`. These include original sector padding. After further method translations, execution reaches the memory-card dialog. The ninth supplied bundle completes `/MEDIA/MISSION/MSSN10XX/MSSN1010.DAT` and padding. Further execution waited during Sofdec movie initialization in both 90- and 120-second runs. After correcting the thread-resume return value described below, its worker requests OGRE2.CVM offset `0x97664800`, length `0x100000`: the first 1 MiB of `/MEDIA2/MOVIE/SEGALOGO.SFD`. The original index gives that movie a total size of 30,283,776 bytes. No missing dispatch target is reported at this data stop. This permits small Windows uploads while tracing initial asset needs; it does not supply the complete archives or establish a playable boot or memory-card behavior.

## Full-runtime GAME activation

[prepare_boot_overlays.py](../tools/prepare_boot_overlays.py) rechecks each private overlay's original instruction digest, payload SHA-256 and saved analysis proof, then validates its generated registration. It produces separate object libraries and sparse dispatch bindings outside the checkout. GAME currently has 1,750 decoded ranges, 141,462 instructions and 94,618 callable entries, including original constructors and indirect aliases. Generation reports zero errors; unresolved control-flow warnings remain.

The host intercepts the original initializer at `0x00100350` only for the shared gameplay slot. Before invoking that original code, it verifies the complete loaded image and installs only the matching overlay's functions into PS2Runtime's dense table. The adapter clears the entire shared slot on replacement, without writing guest RAM, so the original loader retains BSS clearing and constructor execution. The native trace verifies the 704,896-byte GAME image, passes the observed indirect callback at `0x00696950` and reaches the SEGA logo read. Other module activations remain to be exercised. See [overlay research](overlays.md).

After that read, execution reached GAME method `0x006a1390` through the original resident table at `0x00148620`. The supported SLES_541.71 SHA-256 and the complete 15-word table were checked before seeding its two previously unidentified GAME methods, `0x006a1390` and `0x006a13a0`. All thirteen method pointers were checked against the original GAME image. The regenerated map retains all 94,615 previous callable entries and adds three entries, including aliases. No guest instructions or return values were replaced. The next run passed these calls and reached the `TALK_MEMCARD.BIN` data stop. That asset is now supplied; subsequent resident translations allow the original dialog to execute.

## Native kernel compatibility

The original CRT calls SDK initialization at `0x0010f518`. Its firmware discovery routine at `0x0010f408` installs FindAddress/copy handlers and searches the physical PS2 kernel for a syscall table. With no PS2 firmware kernel in the native runtime, this loops at `0x0010f490`. The initial unmodified boot attempt reached this loop and stopped at the configured time limit.

Four PAL-specific hooks replace firmware patch installers at `0x0010f408`, `0x0010f9f8`, `0x0010f640` and `0x0010eb30`. These installers locate or copy MIPS code into firmware kernel addresses and replace firmware handlers. PS2Recomp provides native EE kernel services instead. The hooks are applied only after validating the PAL inputs and confirming the mapped entry points. They are explicit compatibility adaptations, not evidence that a physical PS2 kernel was executed or validated.

Original libc semaphores, timer initialization, the kernel top-thread setup and the final initialization structure still execute as translated guest code. Unresolved functions remain fatal; the diagnostic does not enable the runtime's missing-call skip policy.

## Observed SDK interfaces

The PAL SDK's physical SIF command handshakes, CDVD RPC clients and DECI2 debug console cannot complete against a native host. The verified entry points now route to PS2Recomp's implemented native services. The bindings retain the original arguments and return address, including scheduler continuation semantics.

The native FIO backend performs the real MAIN file reads. The virtual CD backend finds IRX.DAT and completes real sector reads synchronously; CD error queries report its host-file result. IOP heap allocations use the runtime allocator. The DECI2 console writes the actual original message bytes to the host console. Readiness responses come from the native backend, without executing physical PS2 firmware or the IOPRP300 system modules.

The module-start bridge retains the original EE-to-IOP DMA operation. Before executing a transferred module, it compares every transferred byte against its EE source and checks that all ELF tables and file-backed sections fit the transfer. It then invokes the real IOP module loader with that verified source and returns the actual module ID and start result to the game. All nine supplied driver modules started through this path in the Linux full-runtime run; audio output, controls and memory-card operation remain unverified.

Command initialization also initializes the native RPC state before clients bind. The distinct routine at `0x0010a028` is fileXio initialization for SID `0x80000001`; its native binding checks the mounted disc directory. The observed fileXio device-control call at `0x0010cdd0` probes `hdd0:` and `hdd1:` with command `0x4807`. This host has no PS2 HDD device, so those requests return `-ENODEV` (`-19`) and the original detection continues. Other device-control requests remain explicit unsupported errors.

The PAL vertical-blank helper at `0x001056c0` registers two stack-local pointers with SetVSyncFlag and then polls INTC_STAT. The native MMIO poll can finish before the queued display event writes those locals. A trace caught that later write changing a saved return address from `0x0041b340` to `1`, followed by an invalid branch. The helper now waits for the scheduler's actual next vertical blank and returns GS CSR, preserving the 64-bit SDK result whose caller extracts FIELD at bit 13. It registers no temporary stack pointers. Bounded continued runs with the fix reach the frame loop without that invalid return; this does not establish a visible PAL selection screen or full controller support.

The runtime's call dispatcher also treated an unchanged entry PC as an implicit function return. During recursive guest calls, a scheduler safe point can leave PC at that same address while an outer guest stack frame remains active. Returning to the caller at that point corrupts subsequent stack restoration. The PAL runtime adaptation requires an explicit return to the caller PC instead. A synthetic regression forces this recursive yield: it fails with the pinned dispatch behavior and passes with the adaptation. Native SDK wrappers already set their return PC explicitly.

The original CRI critical section saves the return value of `ChangeThreadPriority`, temporarily raises the calling thread to priority 1, then restores the saved priority. The pinned syscall wrapper returned zero on success, so restoration requested invalid priority zero and left the main thread ahead of the ready I/O workers. The private runtime adaptation returns the previous priority on success from both ordinary and interrupt-safe variants, preserving actual negative errors. A display-free regression checks boost/restore and invalid-priority/thread cases; it fails against the pinned behavior. Continued-run diagnostics now include EE thread priorities, states and waiting semaphores to distinguish a scheduler stall from a missing asset.

After `MSSN1010.DAT` loads, the original CRI frame loop at `0x00200c38` resumes its movie worker and compares the result with that worker's ID before calling `WakeupThread`. The pinned `ResumeThread` wrapper returned zero after a successful resume, so the original code skipped the wakeup and the queued movie-open request remained unprocessed. The adapted wrapper returns the actual target ID after successful scheduler completion and preserves negative errors. A synthetic regression checks the wakeup conditional on the returned thread ID, the ordinary and negative numeric syscall forms, and errors for unsuspended and unknown threads. It fails against the previous wrapper.

## VIF image uploads and private graphics diagnostics

The memory-card dialog exposed a VIF1 transfer-boundary bug. Its font texture in GS memory began with eight bytes of VIF commands, followed by the exact original glyph data shifted eight bytes. Its palette was shifted by two 32-bit entries. A GIF IMAGE tag and its pixels can arrive in separate VIF DIRECT commands; the pinned interpreter treated the next VIF command words as pending image bytes.

[prepare_vif.py](../tools/prepare_vif.py) keeps DIRECT payload length separate from pending GIF IMAGE length. It parses the intervening VIF codes, forwards only declared DIRECT payload bytes, retains DIRECT uploads split across DMA/FIFO deliveries, and clears both states on VIF reset. It preserves the original pixels and palette. A display-free synthetic regression compares every transported image byte, includes pixel data resembling commands, and checks split deliveries, continuation through multiple DIRECT commands, the following command and reset. The test fails against the previous interpreter. In a subsequent original-game run, the entire 32,768-byte font texture and 64-byte palette in GS memory match their EE sources exactly. Captured dialog text is readable. That run advanced to the then-missing `MSSN1010.DAT` sector; this verifies the observed upload and dialog, without establishing complete graphics correctness.

For local graphics debugging, set `YAKUZA_BOOT_DUMP_GS=1` before a continued run. At shutdown, the host writes `state/graphics/gs-trace.txt`, `gs-vram.bin` and `ee-ram.bin` beneath the selected state directory. The text includes recent GS events and texture state; the binary snapshots contain 4 MiB of GS VRAM and 32 MiB of emulated EE RAM. These diagnostics contain original game data and belong outside the public checkout. Recording is disabled by default. In PowerShell:

```powershell
$env:YAKUZA_BOOT_DUMP_GS = "1"
# Run the boot probe with a private state directory, then disable recording:
Remove-Item Env:YAKUZA_BOOT_DUMP_GS
```

With `YAKUZA_BOOT_TRACE_MOVIE=1`, the continued probe also traces selected original PAL movie and thread calls. It logs bounded samples, caller/argument addresses, movie mode and queue state, and final call totals. Each observer invokes the original entry once and retains scheduler continuations. A return trace with `returned=0` can indicate a yield or a transfer to another decoded chunk. Thread snapshots include suspend/wakeup counts and callback depth. This diagnostic is disabled by default.

## IPU input and the MPEG wait helper

With the supplied movie input, the original parser stalled while searching for an MPEG start code. Its cached input was `0x40000008`, the FDEC command it had issued. The pinned memory handler stored the command word and returned it as decoded data; it did not consume an IPU input stream.

[prepare_ipu.py](../tools/prepare_ipu.py) connects the private memory implementation to [ipu_bitstream.cpp](../src/ipu_bitstream.cpp). The input path handles CPU FIFO delivery, fixed-length bit peeks/advances, input waits, bit position, reset and quantization/VQ table input. Normal and supported source-chain TO_IPU transfers retain FIFO backpressure, update MADR/QWC/TADR and report actual DMA completion. The regression exercises synthetic MPEG start codes, unaligned reads across qwords, empty-input BUSY, normal DMA, REF/END chains, table consumption and out-of-bounds rejection. It fails against the previous memory handler and passes with the adaptation.

The original wait helpers load the 64-bit IPU_CMD or IPU_TOP DATA/BUSY pairs, then test their signs. The pinned translation used `GPR_S32` for the branches at `0x0012a678` and `0x00129644`, ignoring BUSY in bit 63. [prepare_ipu_wait.py](../tools/prepare_ipu_wait.py) verifies both complete generated helpers by SHA-256, preserves their original generated source privately and changes those native conditions to `GPR_S64`. It rejects other source changes and is idempotent. Original MIPS instructions remain unchanged.

An original-game run with both corrections passes the start-code loop and reaches picture dispatch. [SeedMpegPictureCases.java](../tools/ghidra/SeedMpegPictureCases.java) verifies the original JR and all five table words at `0x00139db0` before identifying the four distinct branch entries. This retains every previously callable address and adds the missing picture cases and their continuations.

The input path also decodes macroblock addresses, picture-dependent macroblock types, motion codes and differential vectors. Tests cover standard codewords, escape/stuffing rules, signed results, following bits and invalid-symbol status. A specific native device error passes through the runtime memory helpers so an unsupported capability cannot be converted into an EE address exception. A regression through the real 32-, 64- and 128-bit store helpers fails before that correction and passes after; ordinary guest address errors retain their existing behavior.

[ipu_block.cpp](../src/ipu_block.cpp) implements incremental BDEC decoding of intra and residual macroblocks: DC prediction, quantization, VLC/escape coefficients, scan order, integer IDCT and frame/field placement. FROM_IPU DMA transfers the resulting 384 signed 16-bit Y/Cb/Cr samples to main RAM or scratchpad, with FIFO backpressure and actual channel completion. Synthetic tests check known uniform and AC pixel values, signed residuals, the original game's alternate-VLC/DC-precision flags, input starvation, late output DMA and destination bounds. The tables and scalar IDCT retain their PCSX2/libmpeg2 credits.

Original movie execution now passes BDEC output transfers and reaches its motion-compensation callbacks. [SeedMpegMotionEntry.java](../tools/ghidra/SeedMpegMotionEntry.java) verifies all 148 bytes of the observed callback before recovering code previously marked as data. [SeedMpegMotionTable.java](../tools/ghidra/SeedMpegMotionTable.java) verifies all 16 original pointers before identifying the remaining entries. Existing callable addresses and instruction bytes remain preserved.

RGB32 CSC consumes the declared number of Y/Cb/Cr macroblocks and emits RGBA using the documented integer conversion and threshold rules. Tests check black/white and colored quadrants, chroma subsampling, alpha boundaries, multiple blocks, output backpressure and exact DMA counts. Original execution completes full-frame conversions. After bundle 12 supplied the remaining movie extent, continued runs pass the earlier missing read. This native path is shared by Linux and Windows and does not require FFmpeg.

IDEC, RGB16 CSC and PACK commands remain unsupported and stop explicitly. Correct movie reconstruction and on-screen presentation remain unverified; completed DMA transfers alone do not establish correct playback.

## Scratchpad source-chain DMA

The original motion-compensation helper at `0x0012ac78` builds REF/REFE tags and starts channel 9 with CHCR `0x105`. The pinned runtime handled normal scratchpad copies, but ignored source chains; polling then cleared STR without transferring their bytes. A synthetic chain reproduces the missing copy before the correction.

[prepare_spr.py](../tools/prepare_spr.py) connects the verified private memory implementation to [scratchpad_dma.cpp](../src/scratchpad_dma.cpp). It transfers REF/REFE and supported inline/jump tags, wraps the scratchpad address, advances MADR/QWC/TADR/SADR and signals actual completion. Tests exercise tag bytes versus payload bytes, CNT/NEXT/END, TIE/IRQ termination, scratchpad-resident tags, invalid source bounds and native errors through the real runtime store helper. Unsupported modes stop explicitly. Ordinary guest address faults retain their existing behavior.

With this correction, a recovered column-major Y/Cb/Cr frame matches frame 31 of an independent MPEG decode: 2,788 of 294,912 samples differ, with a maximum difference of one. A later recovered frame matches frame 241 with the same maximum difference in all three planes. These checks verify selected decoded frames rather than complete playback. Longer development captures can request up to 1,800 seconds; the default remains 15 seconds.

## Host controller adapter

The original PAL device bus uses DBC_Manager and ds2u_d, rather than the standard libpad calls. The adapter observes successful original controller-open RPC replies and retains their actual port/handle mapping. It leaves original IOP module loading and open operations intact. Three identified SDK calls use the host backend for the first logical port: readiness at `0x001263a0`, capabilities at `0x001262d0` and input data at `0x001261f8`. The original SDK active-handle flag must still be set.

The adapter converts the native 32-byte PS2-format sample into the PAL 28-byte button/axis packet and 32-byte capability packet. It advertises sixteen digital buttons and four analog axes; pressure and rumble are not implemented. Other logical ports remain disconnected. Unit checks cover held/released buttons, axis ordering, digital-mode stick centering, unsupported samples and capability flags.

In an internal Linux test, a real X11 X key press changed the sample from `ffff` to `bfff` (Cross held) and original execution left the PAL selection loop. This is evidence for that input path, not complete controller or Windows gameplay validation. Host keyboard mappings currently come from the pinned backend: X/Space for Cross, Enter for Start, arrow keys/WASD for the D-pad. Windows execution and physical gamepad behavior remain unverified.

## Newly discovered resident code

The first constructor pass revealed a missing entry at `0x0013a2a0`. Its address comes from the original resident constructor table at `0x0013a304`. [SeedResidentCtor.java](../tools/ghidra/SeedResidentCtor.java) checks that pointer before changing Ghidra analysis metadata. It preserves all original bytes.

[prepare_boot_supplement.py](../tools/prepare_boot_supplement.py) verifies the updated instruction digest against the byte-preserving PAL analysis image and rejects removed baseline coverage. The v42 supplement translates 2628 instructions in 155 ranges, including the resident constructor and identified graphics, input, filesystem and object methods. Generation reports zero errors and twelve unresolved indirect-control-flow diagnostics, each emitted twice. Its synthetic ELF header entry is adjusted for partial registration; loaded instruction bytes are unchanged. `YAKUZA_BOOT_SUPPLEMENT_DIR` adds its dispatch entries without replacing existing resident/MAIN mappings. When a newly identified method shares decoded bytes with an old chunk, registration checks the original address/slot pairs and preserves those existing mappings.

Pass `--previous-supplement /path/to/earlier-pass` when preparing a later supplement. This option carries forward identified entries and checks that their earlier code remains covered. It can be repeated to combine older passes. Preserving decoded bytes alone is insufficient: a newly callable entry inside those bytes can otherwise disappear from the next dispatch map. A regression reproduces that omission and verifies entry retention.

[SeedCvmCallbacks.java](../tools/ghidra/SeedCvmCallbacks.java) verifies all 25 words of the original CVM interface table at `0x0044e680` before classifying its 17 nonzero callbacks. The original archive-open and seek calls reached this table after the private boot-data ZIP was supplied. The script checks executable targets and rejects conflicting function boundaries; it changes analysis metadata only. Include its identified starts with `--entry` when preparing their first supplement, then retain them with `--previous-supplement` on subsequent passes.

[SeedBootUpdateCallbacks.java](../tools/ghidra/SeedBootUpdateCallbacks.java) identifies original methods after boot execution reached missing callbacks. It scans only the supported PAL resident bytes and accepts aligned method pointers inside MAIN's primary text. Before editing analysis metadata, it verifies five complete SHA-256 catalogs: 240 seven-word tables sharing final method `0x0026ea10`, eleven six-word tables sharing `0x0029e4b0`, five seven-word interface tables at `0x0013d5d0`, `0x0013d5f0`, `0x0013d610`, `0x0013da00` and `0x0013dad0`; three five-word tables at explicit addresses `0x001427e0`, `0x00142800` and `0x00142820`; and a 31-word interface table at `0x0013da20`. The seven-word set includes callback `0x00242da0` reached after reading `SEGALOGO.DAT` and `0x00250310` reached after reading `TALK_MEMCARD.BIN`. The larger table contains 29 methods, including observed callback `0x0024cf80`. Its adjacent base interface supplies another five methods. All cataloged method addresses are checked against the generated registration before a new boot attempt. The five-word set includes the table used by the object at `0x00157458`, which reached missing methods before and after the `MSSN1000.DAT` read. Together these contain 748 distinct methods, many already identified by earlier analysis. Explicit locations must be ordered, aligned and within resident bounds. The script checks executable targets and rejects conflicting function boundaries, then identifies remaining function entries. Changed-table checks reject altered catalogs before creating functions; repeating the script on the supported analysis identifies zero further entries. Original empty methods retain their return instructions. Pass newly callable starts with `--entry` and retain the resulting supplement as above.

The graphics method at `0x0018fda0` is referenced by the original vtable word at `0x0013a914`. Its bytes were already decoded at the end of another chunk, but had no callable registration. [SeedGraphicsEntry.java](../tools/ghidra/SeedGraphicsEntry.java) checks the vtable pointer before classifying the function. The supplemental generator's `--entry 0x18fda0` preserves that newly identified entry even though no new instruction bytes were discovered. It does not replace the original method's return value with an invented result.

[SeedObservedEntry.java](../tools/ghidra/SeedObservedEntry.java) handles additional indirect entries observed in verified boot traces. It checks the original first instruction before changing analysis metadata and rejects conflicts with classified functions. Earlier callback `0x0017eb40` came from a runtime JALR target; its original code then reached the PAL_NTSC.DAT read. After the first opening-movie chunk loaded, another JALR reached callback `0x001b9af0`. Seeding its distinct ten-instruction range preserves every prior callable address. The entire supplied 1 MiB movie chunk matches its copy in EE RAM; this verifies transport, while decoding and presentation remain unverified.

The next original-game run passes that callback and reaches the following movie read at `OGRE2.CVM:0x97764800:0x31000`. Bundle 11 now supplies this 196 KiB refill, which also matches its entire copy in EE RAM. Execution then reaches callback `0x001f7598` from JALR `0x001f86e4`. Seeding its original seven-instruction range retains all 331,612 previously callable resident/MAIN addresses and adds this entry without changing guest instructions.

After the scratchpad transfer correction and native-device optimization, execution also reaches movie-output callback `0x001d6160` from JALR `0x001e5bdc`. Its original return and delay-slot instructions are translated unchanged. A later call from the same dispatcher reaches `0x001e6eb0`. [SeedMovieOutputCallbacks.java](../tools/ghidra/SeedMovieOutputCallbacks.java) verifies the complete 30-word driver descriptor catalog at `0x004eb708`, covering three driver variants and seven distinct interfaces. It checks all 98 method slots across those interfaces before identifying 23 missing entries. Seven changed-word checks reject altered descriptors or methods before creating functions, and a supported repeat creates no new entries. The v51 supplement retains all 331,638 previously callable resident/MAIN addresses and adds twelve entries; every verified method pointer is registered. Generation reports zero errors and 24 unresolved-control-flow warnings. The resulting original-code host cross-builds for Linux and Windows x64; this does not establish that every interface executes correctly.

The next Linux run passes both observed callback stops and, with actual host Start input during the movie, reaches `OGRE.CVM:0x31f2000:0x800`. The original PAL index identifies this sector as the complete 800-byte `/MEDIA/MISSION/MSSN10XX/MSSN1020.DAT`, including sector padding. These original bytes are not yet supplied. This verifies progress through the exercised movie-exit path; automatic complete playback and the title screen remain unverified.

Bundle 13 now supplies that sector. The subsequent run completes the read, with all 2,048 bytes matching EE RAM at `0x006f5240`, and reaches the missing 240-byte `/MEDIA2/AUTHOR/OPENING/OPENING_MOVIE.DAT` descriptor. Its original sector starts at `OGRE2.CVM:0x27fed800`; no missing indirect call is observed in this run. The next collection covers it and the adjacent opening-scene companion file.

## PAL native memory layout

The default runtime reserves the top 1 MiB of EE RAM for helpers. MAIN's original allocator then fails a 0x3c3500-byte graphics allocation. Its subsequent cleanup reads an invalid slot and loops. Returning the original PAL heap boundary, 0x1fe0000 below the 128 KiB main stack, makes that allocation succeed and reaches the original PAL display-mode setup call.

[prepare_runtime.py](../tools/prepare_runtime.py) verifies the exact source digests of five adapted upstream files and the memory header, then creates private build copies. All host translation units use the copied headers so they share the adapted memory layout. The source checkout stays intact. [pal-runtime-layout.json](../config/pal-runtime-layout.json) defines disjoint low-memory regions above the native kernel mirrors and below the resident executable at 0x100000:

| Native region | Start | End (exclusive) |
| --- | --- | --- |
| RPC packets | 0x80000 | 0x90000 |
| RPC servers | 0x90000 | 0xa0000 |
| TLS | 0xa0000 | 0xb0000 |
| Boot metadata | 0xb0000 | 0xb1000 |
| Helper heap | 0xb4000 | 0xd0000 |
| Callback stacks | 0xd0000 | 0x100000 |

The generator rejects overlapping regions. MAIN entry configures the separate helper heap only after checking that no prior native heap allocation exists. The original game allocator keeps its own heap. This avoids placing native RPC descriptors or callback stacks inside game allocations; it is a PAL-specific development layout, not an upstream compatibility claim for other games.

## Public CI

GitHub Actions builds the default tools on Windows/MSVC and Linux. A separate Windows host check compiles the full desktop runtime with clearly labeled synthetic code, exercises invalid-input rejection before window creation and checks recursive dispatch yields, priority and resume syscall return values, VIF image boundaries and overlay dispatch replacement without a display. This checks the host build without distributing original game files. It does not boot or validate the game.
