# Full-runtime boot development

The opt-in `yakuza_boot_probe` target links the verified resident/MAIN translation to the full PS2Recomp desktop runtime. It opens a development window and attempts to run the original PAL loader. Its first milestone is reaching `0x0022cc40`, where it deliberately stops before executing the MAIN body. This executable is not a playable release.

Original disc files and generated game source remain outside the repository. The default build does not fetch graphics dependencies or compile game code. Enable this target only when private verified translations are available.

## Windows development build

With Visual Studio 2022's C++ workload, Git, Python 3.10+ and CMake installed, use a developer PowerShell:

```powershell
cmake -S . -B "$env:LOCALAPPDATA\YakuzaRecomp\boot-build" -A x64 `
  -DYAKUZA_BUILD_BOOT_PROBE=ON `
  -DYAKUZA_MAIN_GENERATED_DIR="D:\Yakuza Research\generated-pal-probe" `
  -DPS2X_ENABLE_FFMPEG=OFF
cmake --build "$env:LOCALAPPDATA\YakuzaRecomp\boot-build" --config Debug --parallel 2 --target yakuza_boot_probe
& "$env:LOCALAPPDATA\YakuzaRecomp\boot-build\Debug\yakuza_boot_probe.exe" "D:\Yakuza PAL" 15 "$env:LOCALAPPDATA\YakuzaRecomp\boot-state"
```

The generated directory must contain the real verified resident/MAIN `.cpp` files, registration and headers. The synthetic CI fixture cannot run the game. Put the build outside this checkout because its private registration contains generated game code. The diagnostic validates the supported SLES_541.71 and MAIN.BIN fingerprints before starting the runtime, and the Python runner additionally checks their SHA-256 hashes plus SYSTEM.CNF.

The initial Windows cross-build disables FFmpeg video decoding explicitly. This limits media behavior and is not a completed video implementation. The native Linux development build enables system FFmpeg. Full gameplay graphics, audio and controls remain unverified.

## Internal Linux boot attempt

The cloud's desktop SDK is installed under `/workspace/.cache/yakuza-onboarding/desktop-sdk/root`. Debian Release signatures, the package index and every extracted package checksum are verified. No system installation is needed. The SDK provides X11/OpenGL/FFmpeg development files and Xvfb; the public source does not depend on this particular cloud layout.

```sh
source /workspace/.cache/yakuza-onboarding/activate.sh
export PKG_CONFIG_LIBDIR=/workspace/.cache/yakuza-onboarding/desktop-sdk/root/usr/lib/x86_64-linux-gnu/pkgconfig:/workspace/.cache/yakuza-onboarding/desktop-sdk/root/usr/share/pkgconfig
export PKG_CONFIG_SYSROOT_DIR=/workspace/.cache/yakuza-onboarding/desktop-sdk/root
cmake -S . -B /workspace/scratch/yakuza-pal/boot-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=OFF \
  -DFETCHCONTENT_SOURCE_DIR_PS2RECOMP=/workspace/.cache/yakuza-onboarding/PS2Recomp \
  -DCMAKE_PREFIX_PATH=/workspace/.cache/yakuza-onboarding/desktop-sdk/root/usr \
  -DYAKUZA_BUILD_BOOT_PROBE=ON \
  -DYAKUZA_MAIN_GENERATED_DIR=/workspace/scratch/yakuza-pal/generated-pal-probe
cmake --build /workspace/scratch/yakuza-pal/boot-build --target yakuza_boot_probe --parallel 2
python tools/run_boot_probe.py \
  --exe /workspace/scratch/yakuza-pal/boot-build/yakuza_boot_probe \
  --disc-dir /workspace/library-files/yakuza-pal \
  --out-dir /workspace/scratch/yakuza-pal/new-boot-attempt \
  --seconds 15 \
  --xvfb /workspace/.cache/yakuza-onboarding/desktop-sdk/root/usr/bin/Xvfb
```

Choose a fresh output directory for each run. The runner preserves the executable digest, original input hashes, exit status and trace. Its outer timeout can kill a stuck process if the runtime's cooperative stop fails. The temporary display is shut down afterward. The native run may report no available audio device in the cloud; this does not test sound output. Save-state paths are separate from the original disc files.

## Native kernel compatibility

The original CRT calls SDK initialization at `0x0010f518`. Its firmware discovery routine at `0x0010f408` installs FindAddress/copy handlers and searches the physical PS2 kernel for a syscall table. With no PS2 firmware kernel in the native runtime, this loops at `0x0010f490`. The initial unmodified boot attempt reached this loop and stopped at the configured time limit.

Four PAL-specific hooks replace firmware patch installers at `0x0010f408`, `0x0010f9f8`, `0x0010f640` and `0x0010eb30`. These installers locate or copy MIPS code into firmware kernel addresses and replace firmware handlers. PS2Recomp provides native EE kernel services instead. The hooks are applied only after validating the PAL inputs and confirming the mapped entry points. They are explicit compatibility adaptations, not evidence that a physical PS2 kernel was executed or validated.

Original libc semaphores, timer initialization, the kernel top-thread setup and the final initialization structure still execute as translated guest code. Unresolved functions remain fatal; the diagnostic does not enable the runtime's missing-call skip policy.

## Public CI

GitHub Actions builds the default tools on Windows/MSVC and Linux. A separate Windows host check compiles the full desktop runtime with clearly labeled synthetic code and exercises invalid-input rejection before window creation. This checks the host build without distributing original game files. It does not boot or validate the game.
