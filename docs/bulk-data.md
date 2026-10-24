# Faster private data transfer

Complete original archives let development continue through new file requests without another upload for each small asset. They do not solve runtime compatibility issues. Original game data stays in private development storage.

## Private download link

Upload your own `.iso.gz`, ISO or extracted `OGRE.CVM`, `OGRE2.CVM` and `OGRE3.CVM` to storage you control, then provide a download link through the development session. The chat attachment size limit applies to direct attachments; a link is a separate transfer route. Access and download capability must be checked for the actual link. A sign-in-only link may need a supported storage connector or another authorized download method. Never send account passwords or access tokens.

This is the most convenient route for a disc image of several gigabytes: one external upload can replace many chat attachments. Use a service and sharing scope appropriate for your private files.

## Windows split-ZIP collector

[disc_pack.py](../tools/disc_pack.py) reads an extracted disc folder, ISO or `.iso.gz`, compresses the selected complete archives and splits the compressed ZIP stream into parts of at most **24 MiB**. It scans selected ISO extents in disc order in one session rather than reopening the compressed ISO for every part. It does not require a decompressed ISO copy. Memory use is bounded by small read buffers. ZIP64 supports combined archives and ZIP offsets beyond 4 GiB; the collector is not restricted to a 4 GB ZIP file.

The number of parts depends on compression. A nearly 4 GB compressed disc image would still require many parts if transferred in full. Selecting only `OGRE3.CVM` is a useful starting point for the current enemy/stage-data boundary; its original size is about 1.1 GiB. It includes the presently missing `E434` data and future assets from that archive. Other archives may still be needed later.

Run this from the folder containing your ISO on Windows 10/11, using the Python installation already used by `disc_ranges.py`:

```powershell
New-Item -ItemType Directory -Force .\yakuza-transfer-tools | Out-Null
Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/TatsunaKyo/YakuzaRecomp/main/tools/disc_ranges.py" -OutFile .\yakuza-transfer-tools\disc_ranges.py
Invoke-WebRequest -UseBasicParsing "https://raw.githubusercontent.com/TatsunaKyo/YakuzaRecomp/main/tools/disc_pack.py" -OutFile .\yakuza-transfer-tools\disc_pack.py
python .\yakuza-transfer-tools\disc_pack.py pack --iso ".\Yakuza (Europe) (En,Fr,De,Es,It).iso.gz" --archive OGRE3.CVM --output-dir .\yakuza-ogre3-parts
```

For an already extracted disc folder, replace `--iso "..."` with `--disc-dir "E:\path\to\extracted disc"`. To include additional archives in the same pass, repeat `--archive`, for example `--archive OGRE.CVM --archive OGRE2.CVM --archive OGRE3.CVM`. More archives mean more data to transfer.

The tool prints the number of parts. Supply **every `originals.zip.*` file and `parts.json`** from the output folder privately, in batches if necessary. Individual parts are not complete ZIP files; keep their names and all volumes. Choose a new output folder if rerunning the collector. The source files are read without modification.

## Verify and restore internally

Place all downloaded volumes and their `parts.json` together outside the public checkout, then run:

```sh
python tools/disc_pack.py unpack \
  --parts-dir /workspace/library-files/yakuza-transfer/ogre3 \
  --disc-dir /workspace/library-files/yakuza-pal
```

The importer verifies volume sizes and SHA-256 checksums, the complete ZIP digest, member names, ZIP CRCs and each original archive's size and SHA-256. It compares the restored bytes with every previously supplied excerpt from that archive. All selected files are staged and verified before publishing complete `.CVM` files to the private disc folder. Existing differing originals are preserved and reported as a conflict. Prior excerpt records remain available.

The native reader already gives a complete original `.CVM` priority over partial excerpts, so the transfer format needs no native runtime change. Resume boot validation after restoration; this workflow does not supply a playable game build.
