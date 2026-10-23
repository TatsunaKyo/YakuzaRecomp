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

Bundle 14 supplies both opening-scene files. The next run reads both sectors and reaches `/MEDIA2/MOVIE/OPENING_MOVIE.SFD`, a separate 59,004,928-byte cinematic. The first missing read is `OGRE2.CVM:0x93e1f000:0x100000`. The complete indexed file fits three collections: `OGRE2.CVM:0x93e1f000:0x1800000`, `OGRE2.CVM:0x9561f000:0x1800000` and `OGRE2.CVM:0x96e1f000:0x845800`. Each stays within the existing range, ZIP and upload limits. These requested bytes are not yet supplied; playback of this cinematic remains unverified.

Bundles 15 through 17 now supply all three parts. Their combined length matches the complete indexed `OPENING_MOVIE.SFD`; both this cinematic and the earlier `SEGALOGO.SFD` are available privately. After import, execution reaches an opening-scene interface callback before the cinematic read completes. Further translation is in progress; supplying the data does not establish successful playback.

After further interface translations, the Linux host reads the new movie and renders moving footage. Actual Start input exercises its exit and reaches `MSSN1040.DAT` at `OGRE.CVM:0x31f2800:0x800`. The next collection covers the complete small `/MEDIA/MISSION/MSSN10XX/` group: 49 indexed files in one contiguous 100,352-byte range, `OGRE.CVM:0x31f0000:0x18800`. This includes the observed missing sector and earlier supplied mission sectors; overlap must agree. Other files in the group are included to reduce repeated small uploads and have not all been requested by execution yet.

## Import and run internally

```sh
python tools/disc_ranges.py import \
  --bundle /path/to/yakuza-boot-data.zip \
  --disc-dir /workspace/library-files/yakuza-pal
```

Imported records stay under `.yakuza-disc-ranges` in the private disc folder. The opt-in boot host loads them automatically. A complete original archive takes priority when available. Only the four known OGRE archive names are accepted; supported game executables remain subject to the normal PAL verification.

Each record contains a versioned header, original file size, byte offset, payload size and FNV-1a integrity value, followed by the unchanged bytes. The importer checks paths, sizes, integrity and overlapping data before writing. The C++ reader also validates records, sizes and overlap consistency. A checksum establishes record integrity, not the identity or authenticity of an entire archive. The runner records SHA-256 hashes of the actual supplied excerpt files.

Reads validate complete coverage before touching guest RAM. A hole stops execution explicitly; only padding beyond the real end of the final CD sector can be zero-filled. There are no invented asset payloads. Streaming and other unobserved archive access paths are not validated by these checks.
