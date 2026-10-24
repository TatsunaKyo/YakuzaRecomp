YakuzaRecomp - Windows x64 IOP diagnostic
Project lead and maintainer: TatsunaKyo
Source: https://github.com/TatsunaKyo/YakuzaRecomp

This console development tool checks the original PS2 drivers using your own
IRX.DAT. Game boot, graphics, audio output and gameplay require further work.
No original game files or translated game code are included in this package.

Extract the ZIP, open PowerShell in its folder and run the following, replacing
the example with the path to your extracted PAL IRX.DAT. Press Enter after
each line; do not append $LASTEXITCODE to the executable command:

  .\yakuza_iop_probe.exe "D:\Yakuza PAL\IRX.DAT" > .\probe.txt 2>&1
  $LASTEXITCODE

Windows PowerShell can label redirected stderr logs as NativeCommandError.
Check the final exit code and module results as well as the log.

Keep probe.txt and the displayed exit code. The Linux startup baseline reports
nine loaded modules, 15 threads and eight RPC servers. A minimal-host message
about SIF not being initialized is present in that baseline.

build-info.json records the exact source commit and executable SHA-256.
The package uses the Release static MSVC runtime. Linux, WSL, Python and
Visual Studio are not needed to run this diagnostic.

Yakuza is owned by SEGA and its respective rights holders. The open-source IOP
framework is provided by PS2Recomp and its contributors. See COPYING and
THIRD_PARTY_NOTICES.md for licenses and further credits.
