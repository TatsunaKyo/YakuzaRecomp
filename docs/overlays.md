# PAL overlay research

The supplied OGRE4.CVM is 4,368,384 bytes, SHA-256 `942c7e9cbf35e6ad5ff10aeaf76bb42c6d0f7852b3a2ea0d8630a2eb51e51373`. It contains eleven MWo3 overlays. Each is loaded, including its 64-byte header, at `0x0062dc80`. They are mutually exclusive. Their module IDs select separate LOAD records in the original resident ELF, whose memory sizes exactly match each file plus its BSS. The largest slot ends at `0x006ef500`.

The second payload region mixes data and executable initialization code. Its constructor table contains 50 pointers across the eleven modules. Treating that region as ordinary data would omit these functions. The first nonzero word in the text region is used as an analysis seed; this is not evidence of a gameplay entry-point ABI.

## Reproducing the analysis internally

These Linux commands use the cloud's prepared tools. The player's Windows installation does not need Linux, WSL or Ghidra. Keep all inputs, generated game source and output files outside Git.

```sh
python3 tools/prepare_game.py extract-overlays \
  --disc-dir /workspace/library-files/yakuza-pal \
  --out-dir /workspace/scratch/yakuza-pal/overlays
python3 tools/overlay_image.py prepare \
  --disc-dir /workspace/library-files/yakuza-pal \
  --extracted-dir /workspace/scratch/yakuza-pal/overlays \
  --out-dir /workspace/scratch/yakuza-pal/overlay-analysis-v1
python3 tools/overlay_image.py analyze \
  --out-dir /workspace/scratch/yakuza-pal/overlay-analysis-v1 \
  --ghidra /workspace/.cache/yakuza-onboarding/bin/ghidra-headless \
  --recompiler /workspace/.cache/yakuza-onboarding/build/ps2xRecomp/ps2_recomp
```

Reuse valid retained analysis instead of reimporting it. For a changed analysis, choose a fresh output directory; logs and generated metadata deliberately refuse replacement. `prepare` is repeatable with unchanged files. `analyze` accepts `--module game` to select a prepared module. Each module has its own Ghidra project and prefix, avoiding duplicate native function symbols at shared addresses.

The Python verifier hashes every exported instruction together with its PS2 address and checks it against the original overlay's byte-preserving ELF view. It also checks every seed, section bounds and range ordering. Translation has no forced stubs, skip list or instruction patches. Across the eleven overlays it processed 10,348 ranges and 865,866 decoded instructions, with zero unhandled instructions, decode failures or errors. **7,460 control-flow warnings remain**, and unknown/undecoded code remains possible.

## Native loader and execution check

`OverlaySlot` validates MWo3 extents and constructor pointers before modifying RAM. Activation copies the whole original file, clears that module's BSS and replaces the entire native entry table. A shorter replacement cannot retain callable entries from its predecessor. Invalid input leaves both RAM and active dispatch unchanged. Activation must occur while the EE thread is stopped, outside translated code.

The loader is a standalone integration component. The full PS2Runtime's dense function table, disc-read path, constructor calls and EE scheduler still need to be connected to it. Compiling all overlays into one permanent address table would dispatch the wrong module.

```sh
source /workspace/.cache/yakuza-onboarding/activate.sh
cmake -S . -B /workspace/scratch/yakuza-pal/project-build \
  -DFETCHCONTENT_SOURCE_DIR_PS2RECOMP=/workspace/.cache/yakuza-onboarding/PS2Recomp \
  -DYAKUZA_OVERLAY_ANALYSIS_DIR=/workspace/scratch/yakuza-pal/overlay-analysis-v1
cmake --build /workspace/scratch/yakuza-pal/project-build --parallel 2
ctest --test-dir /workspace/scratch/yakuza-pal/project-build --output-on-failure
/workspace/scratch/yakuza-pal/project-build/yakuza_overlay_native_probe \
  /workspace/scratch/yakuza-pal/overlays/MEDIA4/MODULE
```

The probe loads all eleven original files and verifies payload copies and BSS clearing. It then executes three small real translated routines: GAME at `0x006426e0` (half/clamp plus field writes), HEALTH at `0x0062dd00` (signed RAM load in the return delay slot), and UFOCATCHER at that same guest PC (zero return). It passed 768 cases over 24 subsequent activations, testing branch-likely behavior, delay slots, sign extension and dispatch replacement. Hardware paths fail rather than supply fabricated device results. These routines do not call the scheduler or other guest functions. The probe does not execute constructors or represent a game boot.

The same target cross-builds with the Windows toolchain, including Unicode command-line paths. Windows execution remains unverified. If built on Windows, its command is:

```powershell
.\yakuza_overlay_native_probe.exe "D:\Yakuza Research\overlays\MEDIA4\MODULE"
```

Further work needs full-runtime integration, missing indirect targets and original archive assets. Rendering, sound, controls, saves and gameplay remain unverified. OGRE.CVM, OGRE2.CVM and OGRE3.CVM are not present in this environment; no additional upload is needed to reproduce the checks above.
