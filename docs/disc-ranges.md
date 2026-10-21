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

The initial excerpts let the native reader mount the original logical archive sizes and attempt real reads. They may not include the first asset the game requests. If another read needs missing bytes, the trace stops with `yakuza-disc:missing-range`, recording archive, byte offset and length. Collect the exact logged range with `--range ARCHIVE:OFFSET:LENGTH`, accepting decimal or `0x` values. Requests larger than 24 MiB must be divided into smaller adjacent ranges; each ZIP is limited to 28 MiB. Keep every original archive unchanged between collections.

## Import and run internally

```sh
python tools/disc_ranges.py import \
  --bundle /path/to/yakuza-boot-data.zip \
  --disc-dir /workspace/library-files/yakuza-pal
```

Imported records stay under `.yakuza-disc-ranges` in the private disc folder. The opt-in boot host loads them automatically. A complete original archive takes priority when available. Only the four known OGRE archive names are accepted; supported game executables remain subject to the normal PAL verification.

Each record contains a versioned header, original file size, byte offset, payload size and FNV-1a integrity value, followed by the unchanged bytes. The importer checks paths, sizes, integrity and overlapping data before writing. The C++ reader also validates records, sizes and overlap consistency. A checksum establishes record integrity, not the identity or authenticity of an entire archive. The runner records SHA-256 hashes of the actual supplied excerpt files.

Reads validate complete coverage before touching guest RAM. A hole stops execution explicitly; only padding beyond the real end of the final CD sector can be zero-filled. There are no invented asset payloads. Streaming and other unobserved archive access paths are not validated by these checks.
