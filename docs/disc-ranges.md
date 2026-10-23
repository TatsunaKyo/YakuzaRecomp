# Small private archive uploads

The PAL boot trace now searches for OGRE.CVM, OGRE2.CVM and OGRE3.CVM. They contain several gigabytes altogether. During development, the boot probe can instead read small original excerpts from these archives and report exactly which further bytes it needs. This is a development aid; full gameplay still requires the original assets.

## Collect on Windows

Use Python 3.10 or newer. Download the current [disc_ranges.py](https://raw.githubusercontent.com/TatsunaKyo/YakuzaRecomp/main/tools/disc_ranges.py) into a folder, or update the repository and use its `tools/disc_ranges.py`. The standalone script uses only Python's standard library.

For an ISO or gzip-compressed ISO, run this in PowerShell from the script's folder, replacing the image path:

```powershell
py -3 .\disc_ranges.py collect --iso "E:\Games\Yakuza (Europe).iso.gz" --output ".\yakuza-boot-data.zip"
```

The tool reads the ISO9660 filesystem directly from `.iso` or `.iso.gz`. It scans compressed data to reach the requested files, which may take several minutes. It keeps memory bounded and writes only the small ZIP; it does not create a decompressed ISO or modify the source image. Normal 2048-byte-sector PS2 ISO images are supported. Raw sector images, interleaved files and multi-extent ISO files are unsupported.

For an already extracted disc folder:

```powershell
py -3 .\disc_ranges.py collect --disc-dir "D:\Yakuza PAL" --output "$env:USERPROFILE\Desktop\yakuza-boot-data.zip"
```

The folder or ISO root must contain the original PAL OGRE.CVM, OGRE2.CVM, OGRE3.CVM and OGREDIR.BIN. The command verifies the supported index, reads the archive sizes and copies the first 64 KiB of each, plus the first requested asset, `/MEDIA/SE/00000_CMN.DAT`. The index places that 292864-byte asset at byte offset 106305536 in OGRE.CVM. All four excerpts total less than 500 KiB before compression. The command does not modify the archives or overwrite an existing ZIP. Upload that ZIP privately to the development session. Do not commit it or its contents to GitHub.

The initial excerpts let the native reader mount the original logical archive sizes and complete the observed `00000_CMN.DAT` read. If another read needs missing bytes, the trace stops with `yakuza-disc:missing-range`, recording archive, byte offset and length. Collect the exact logged range with `--range ARCHIVE:OFFSET:LENGTH`, accepting decimal or `0x` values. Requests larger than 24 MiB must be divided into smaller adjacent ranges; each ZIP is limited to 28 MiB. Keep every original archive unchanged between collections.

The second supplied bundle covers `/MEDIA/TALK/SCENARIOSTATEDATA.BIN` at OGRE.CVM offset `0x2063e800`. Its 65536-byte read, including sector padding around the 63564-byte payload, now completes.

The third supplied bundle covers `/MEDIA/PLAYERPOS/PLAYERPOS.BIN` at OGRE.CVM offset `0x6545000`. Its 34816-byte read, including sector padding around the 34084-byte payload, also completes.

The fourth supplied bundle covers `/MEDIA/TALK/NOWLOADING/TALK_NOWLOADING.BIN` at OGRE.CVM offset `0x20ca0000`. Its 4096-byte read completes, including padding around the 2972-byte payload. Continued execution then revealed missing object callbacks; the supplemental translation now gets past those observed calls.

The fifth supplied bundle covers `/MEDIA/CSE/BRI/CSE_STAY.DAT` at OGRE.CVM offset `0x10ce800`. Its 43008-byte read completes, including padding around the 42864-byte payload. Further interface-method translations get through the next observed callbacks.

The sixth supplied bundle covers `/MEDIA/MISSION/MSSN10XX/MSSN1000.DAT` at `OGRE.CVM:0x31f0000:0x800`. Its 2048-byte sector read completes, including padding around the 1040-byte payload.

The seventh through ninth bundles supply `SEGALOGO.DAT` at `OGRE.CVM:0x8d1000:0x51000`, `TALK_MEMCARD.BIN` at `OGRE.CVM:0x207a0000:0x14000` and `MSSN1010.DAT` at `OGRE.CVM:0x31f1800:0x800`. All nine requested asset reads complete. The original memory-card dialog is readable after the VIF transfer correction.

The opening-movie worker then requests the first 1 MiB of `/MEDIA2/MOVIE/SEGALOGO.SFD` at `OGRE2.CVM:0x97664800:0x100000`. Bundle 10 supplies this range. The movie's full indexed size is 30283776 bytes; supplying its first chunk does not establish successful playback.

After translating the next observed movie callback, execution requests the following 200704 bytes (196 KiB) at `OGRE2.CVM:0x97764800:0x31000`. Bundle 11 supplies this range. Both reads complete, and all supplied bytes match their copies in emulated EE RAM. Execution then reaches another indirect callback in the original stream-processing code.

Bundle 12 supplies the remaining 29,034,496 bytes of the indexed opening movie. The complete `SEGALOGO.SFD` is now available privately. Selected reconstructed frames match an independent decode within a one-level sample difference; complete playback remains unverified.

Bundle 13 supplies `MSSN1020.DAT` at `OGRE.CVM:0x31f2000:0x800`. The full sector matches its copy in EE RAM. Execution advances to `/MEDIA2/AUTHOR/OPENING/OPENING_MOVIE.DAT` at `OGRE2.CVM:0x27fed800:0x800`. The next collection includes this sector and the adjacent indexed companion `OPENING_MOVIE.B00` as one 4 KiB range, `OGRE2.CVM:0x27fed000:0x1000`. The descriptor read is observed; the companion is included to reduce separate small uploads.

Bundle 14 supplies both opening-scene files. The next run reads both sectors and reaches `/MEDIA2/MOVIE/OPENING_MOVIE.SFD`, a separate 59,004,928-byte cinematic. The first missing read is `OGRE2.CVM:0x93e1f000:0x100000`. The complete indexed file fits three collections: `OGRE2.CVM:0x93e1f000:0x1800000`, `OGRE2.CVM:0x9561f000:0x1800000` and `OGRE2.CVM:0x96e1f000:0x845800`. Each stays within the existing range, ZIP and upload limits. These bytes were supplied in the following three bundles; playback validation continues separately.

Bundles 15 through 17 supply all three parts. Their combined length matches the complete indexed `OPENING_MOVIE.SFD`; both this cinematic and the earlier `SEGALOGO.SFD` are available privately. The first run after import reached an opening-scene interface callback before the cinematic read completed. The additional translation described below gets past that callback; supplying the data alone does not establish successful playback.

After further interface translations, the Linux host reads the new movie and renders moving footage. Actual Start input exercises its exit and reaches `MSSN1040.DAT` at `OGRE.CVM:0x31f2800:0x800`. Bundle 18 supplies the remaining 44 small files in `/MEDIA/MISSION/MSSN10XX/`: one contiguous 90,112-byte range, `OGRE.CVM:0x31f2800:0x16000`, starting at that sector. It uses a new excerpt filename and preserves earlier imported mission records. Other files in the group are included to reduce repeated small uploads and have not all been requested by execution yet.

The next Linux run reads `MSSN1040.DAT`; its full 2,048-byte sector matches EE RAM. It then requests `/MEDIA/ADVERTISE/TITLELOGO.DAT`, a 389,376-byte asset at `OGRE.CVM:0x922000`. The observed read includes sector padding: `OGRE.CVM:0x922000:0x5f800` (391,168 bytes). Collect it with the existing script:

```powershell
python .\disc_ranges.py collect --iso ".\Yakuza (Europe) (En,Fr,De,Es,It).iso.gz" --range OGRE.CVM:0x922000:0x5f800 --output .\yakuza-boot-data-19.zip
```

Bundle 19 supplies the title-logo range. The next Linux run passes the earlier missing read. Its EE memory copy matches 391,104 of the 391,168 supplied bytes; 64 bytes have changed during execution, so this is not a byte-identical whole-range comparison. The cause of those changes is not established.

Execution then requests `/MEDIA/STGTALK/BRI/ST_RES.BIN`: 7,508 file bytes at `OGRE.CVM:0x166c8000`, read as an 8,192-byte sector range. Bundle 20 supplies this range. Its complete sector range now matches EE RAM. It was collected with:

```powershell
python .\disc_ranges.py collect --iso ".\Yakuza (Europe) (En,Fr,De,Es,It).iso.gz" --range OGRE.CVM:0x166c8000:0x2000 --output .\yakuza-boot-data-20.zip
```

The next observed missing read is `/MEDIA/STAGE/ST_RES/TALK_ST_RES.BIN` at `OGRE.CVM:0x1408e000:0x800`: a 192-byte file with sector padding. This file belongs to a separate stage directory containing ten files in one contiguous 530,432-byte range (518 KiB). The next collection includes that complete group to reduce repeated small uploads:

```powershell
python .\disc_ranges.py collect --iso ".\Yakuza (Europe) (En,Fr,De,Es,It).iso.gz" --range OGRE.CVM:0x1404c800:0x81800 --output .\yakuza-boot-data-21.zip
```

Bundle 21 supplies this complete group. `TALK_ST_RES.BIN` was the observed request; the other nine files were related stage assets included in advance. The next run passes the earlier data stop and loads `ST_RES.DAT`, whose entire 114,688-byte sector range matches EE RAM. The ten group members have not all been observed individually. Execution then reaches a missing stage-resource method; supplemental translation now includes its verified original code. This group differs from the supplied `STGTALK/BRI/ST_RES.BIN`. Title-screen rendering remains unverified.

After the stage-resource translation, execution passes the missing callback and requests `/MEDIA/CSE/BRI/CSE_TITLE.DAT` at `OGRE.CVM:0x1107000:0x13800`. Its 78,688 file bytes occupy a 79,872-byte sector read. The next collection covers the complete 27-file BRI CSE directory, including that observed request, as one 2,320,384-byte range (about 2.2 MiB):

```powershell
python .\disc_ranges.py collect --iso ".\Yakuza (Europe) (En,Fr,De,Es,It).iso.gz" --range OGRE.CVM:0xef0800:0x236800 --output .\yakuza-boot-data-22.zip
```

Bundle 22 supplies this group. The importer verifies its overlap with the previously supplied `CSE_STAY.DAT` and keeps the earlier records. The other files are grouped to reduce further uploads and have not all been requested by execution. The range starts at a new offset, avoiding an existing excerpt filename.

The next native run passes `CSE_TITLE.DAT` and requests `/MEDIA2/BGM/TITLE.ADX` at `OGRE2.CVM:0x4b654800:0xc800`. This is the first 51,200-byte read of a 2,058,240-byte title-music stream. The next collection includes the complete stream plus the adjacent `TITLE_CHAP.ADX` and `TITLE_ORDER.ADX` files in one 2,484,224-byte range (about 2.4 MiB):

```powershell
python .\disc_ranges.py collect --iso ".\Yakuza (Europe) (En,Fr,De,Es,It).iso.gz" --range OGRE2.CVM:0x4b654800:0x25e800 --output .\yakuza-boot-data-23.zip
```

Bundle 23 supplies all three tracks. Independent complete ADX decodes pass, and the native run completes the first 51,200-byte `TITLE.ADX` read with an exact match in EE RAM. This does not establish native audio playback or complete streaming. Only the main track request has been observed.

The next missing read is `/MEDIA/TALK/TITLE/TALK_TITLE.BIN`, a 5,024-byte file at `OGRE.CVM:0x216e8800`, read as 6,144 bytes with padding. The next collection includes its adjacent `TALK_CHAPTITLE.BIN` companion: both complete indexed files fit one 26,624-byte range (26 KiB):

```powershell
python .\disc_ranges.py collect --iso ".\Yakuza (Europe) (En,Fr,De,Es,It).iso.gz" --range OGRE.CVM:0x216e3800:0x6800 --output .\yakuza-boot-data-24.zip
```

Bundle 24 supplies both complete files. Native execution passes the title-text read and renders the original Start prompt and main menu. Selecting New Game reaches a missing original callback, whose verified method-table family is now translated. The chapter-title companion has not been requested by execution yet. The title logo and background are absent in the current capture; native audio playback remains unverified.

The v56 host passes the New Game callback and next requests `/MEDIA/ADVERTISE/CHAPTER1.DAT` at `OGRE.CVM:0x158000:0x65000`. Its 412,480-byte file occupies 413,696 bytes with sector padding. Collect the complete related 25-file advertise directory in one 8,701,952-byte range (about 8.3 MiB):

```powershell
python .\disc_ranges.py collect --iso ".\Yakuza (Europe) (En,Fr,De,Es,It).iso.gz" --range OGRE.CVM:0x135000:0x84c800 --output .\yakuza-boot-data-25.zip
```

Upload that ZIP privately. This group includes the already supplied SEGA-logo and title-logo files; their overlapping bytes must match during import. The other chapter and advertise files are included to reduce later uploads and have not all been observed executing. The range starts at a new offset, avoiding an existing excerpt filename.

## Import and run internally

```sh
python tools/disc_ranges.py import \
  --bundle /path/to/yakuza-boot-data.zip \
  --disc-dir /workspace/library-files/yakuza-pal
```

Imported records stay under `.yakuza-disc-ranges` in the private disc folder. The opt-in boot host loads them automatically. A complete original archive takes priority when available. Only the four known OGRE archive names are accepted; supported game executables remain subject to the normal PAL verification.

Each record contains a versioned header, original file size, byte offset, payload size and FNV-1a integrity value, followed by the unchanged bytes. The importer checks paths, sizes, integrity and overlapping data before writing. The C++ reader also validates records, sizes and overlap consistency. A checksum establishes record integrity, not the identity or authenticity of an entire archive. The runner records SHA-256 hashes of the actual supplied excerpt files.

Reads validate complete coverage before touching guest RAM. A hole stops execution explicitly; only padding beyond the real end of the final CD sector can be zero-filled. There are no invented asset payloads. Streaming and other unobserved archive access paths are not validated by these checks.
