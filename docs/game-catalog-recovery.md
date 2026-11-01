# Actual GAME catalog recovery

The retained private Windows callback package at source `fc2938111aaf71d177ab828d9d0f3163f5eee527` contains the actual catalog. Its executable's COFF symbols expose `overlay_entries_0`, the static `compiled_boot_overlays()` descriptor and all GAME owner functions. Original game data and extracted/generated outputs remain private.

| Evidence | Verified result |
| --- | --- |
| Original GAME image | 704,896 bytes; SHA-256 `64b6d4f666a321e682be6becc6d89b37d6c171f0ff3448950a19e7c2ee590c37` |
| Source executable SHA-256 | `fd515fc0922dea62a22b2c07f38ccca09e4810a548ef2470e7e139a0f197bd11` |
| Actual catalog | 95,309 strictly ordered, distinct guest entries; 1,983 native owners |
| Raw catalog table SHA-256 | `0ad30af9b15412333e0bdf0f561fe8ebffcdf606c2df3db0f87171a68aee51a7` |
| Compiled image fingerprint | Matches every byte of the verified original GAME image |
| Historical decoded map | Unavailable; the reported 1,983 ranges / 143,090 instructions are not independently recovered coverage |
| Historical generated C++ bytes | Unavailable; byte equality with regenerated source is unverified |

[recover_game_catalog.py](../tools/recover_game_catalog.py) checks the exact executable and GAME hashes, bounded PE/COFF structures, the accessor's reference to a one-overlay span, the descriptor's identity/size/fingerprint, read-only table storage, executable native pointers, original owner symbols and constructor registrations. A synthetic PE cannot pass the actual recovery's input fingerprints. The original-free parser tests do not establish original-game coverage.

## Original callback provenance

The latest reported Windows stop remains `0x29c4c4 -> 0x69ff50`. Original static bytes establish this chain:

| Location | Original operation |
| --- | --- |
| GAME `0x69fa64`, `0x69fa6c`, `0x69fa74` | Construct `0x1485e0` and store that table pointer at object offset `0x70` |
| GAME `0x6a0084`, `0x6a008c`, `0x6a0094` | Another verified installation of the same table at offset `0x70` |
| MAIN `0x29c4bc` | Load the object's table pointer from offset `0x70` |
| MAIN `0x29c4c0` | Load method slot `0x14` from that table |
| Resident `0x1485f4` | Original slot contains `0x69ff50` |
| MAIN `0x29c4c4`, `0x29c4c8` | JALR and its original NOP delay slot |
| GAME `0x69ff50`, `0x69ff54` | Original `JR $ra` and NOP |

The complete table at `0x1485e0` has two zero headers and six method pointers. Its SHA-256 is `14e99714a445b9a87ea82fb174a755c8b3ade3a3c98106df668396ffdef74b97`. Four methods are absent from the recovered catalog: `0x69ff40`, `0x69ff50`, `0x6a0050` and `0x6a0060`. The recovery translates their original instructions, including the real return/delay-slot behavior at the reported target. Other methods retain their original jumps and calls.

MAIN's actual placement is `0x167c00`, derived from the original resident LOAD's memory extent. Treating MAIN's MWo3 address field as its placement reads different instructions. The recovery explicitly checks this mapping before verifying the caller.

This proves static pointer provenance. A live object/RAM snapshot from the Windows failure is unavailable, and progression past this stop still needs an actual Windows game run.

## Fresh analysis and retained entries

Fresh Ghidra 12.2 / Emotion Engine Reloaded 2.1.39 analysis uses verified owner starts and callable addresses recovered from the executable, plus the four verified table methods. It exports 2,028 ranges and 143,142 instructions, with an address-and-instruction digest checked against the original image. Repeating the public recovery scripts creates no further functions and reproduces the same map and digest.

Translation uses pinned PS2Recomp `eb8688b2fd191129f103a39543002c005b33409c`. The first fresh generation omitted 284 old callable addresses. Entry-point hints, each grounded in the actual recovered catalog and fresh decoded bytes, restore them. The resulting module has **95,347 entries and retains all 95,309 recovered addresses individually**. Generation reports zero errors, decode failures, stubs, skips or unhandled instructions; 1,306 control-flow warnings remain.

The complete regenerated GAME object module compiles on Linux and cross-compiles for Windows x64 with verified LLVM-MinGW 20261006. Actual generated code for `0x69ff40` and `0x69ff50` passes 256 cases across unoptimized/optimized Linux builds, checking the original return PC, full CPU state and unchanged RAM. [The optional original-code harness](../tests/test_recovered_game_returns.cpp) requires the private translations and pinned runtime headers; ordinary CI does not execute these game routines. Cross-compilation is not Windows runtime validation.

The old decoded map and source bytes remain unverified. These fresh counts, build checks and small-method cases do not establish whole-game equivalence, playable performance, correct rendering or Windows runtime stability. The resident/MAIN generated-source tree is also still unavailable, so a complete new game-host build has not been produced.

## Reproduce from the private inputs

```sh
python3 tools/recover_game_catalog.py \
  --exe /private/previous-package/YakuzaRecomp-test.exe \
  --game /private/originals/GAME.BIN \
  --disc-dir /private/disc \
  --out /private/recovery/catalog.json \
  --seeds /private/recovery/seeds.txt \
  --callables /private/recovery/callables.txt
```

Import a byte-preserving GAME analysis ELF with `SeedRecoveredGame.java` as a pre-script, passing the exported seeds and callables. Run `ExportOverlay.java` with its usual CSV/JSON/bounds/prefix arguments followed by that seed file. Verify the exported bytes with `overlay_image.py verify` before invoking the pinned recompiler. Retain any proven missing callable addresses through its `general.entry_points` option, then compare the complete resulting registration against the actual catalog.

For build-time retention, pass `--recovered-executable` and `--recovered-game` to `prepare_boot_overlays.py`, or set `YAKUZA_BOOT_RECOVERED_EXE` and `YAKUZA_BOOT_RECOVERED_GAME` in CMake. The preparer re-extracts the actual catalog from the fingerprinted private executable before writing bindings and checks every recovered address against the fresh decoded map and registration. It rejects a missing old entry even if a new alias preserves the same total count. Its report labels missing historical decoded coverage and C++ source bytes explicitly unverified. Do not substitute the synthetic 95,309-entry test fixture.
