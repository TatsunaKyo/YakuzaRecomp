#!/usr/bin/env python3
"""Run a bounded boot attempt and retain its exit code, trace and milestone.

Windows uses the normal desktop. Internal Linux runs can optionally start an
isolated local Xvfb display; the player does not need this software.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess

from prepare_game import PAL_INPUTS, read_small, require, sha256


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as binary:
        while chunk := binary.read(1024 * 1024): digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--disc-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=15)
    parser.add_argument("--xvfb", type=Path)
    parser.add_argument("--continue-main", action="store_true")
    args = parser.parse_args()
    require(1 <= args.seconds <= 1800 and args.exe.is_file(), "Invalid time limit or missing executable")
    require(not args.out_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
            "Keep boot traces outside the source checkout")
    for name, expected in PAL_INPUTS.items():
        require(sha256(read_small(args.disc_dir / name)) == expected, f"Unsupported PAL input: {name}")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    server = None
    result = {"exit_code": None, "timed_out": False, "reached_main": False,
              "platform": os.name, "time_limit_seconds": args.seconds}
    result["continue_main"] = args.continue_main
    result["exe_sha256"] = file_sha256(args.exe)
    result["input_sha256"] = PAL_INPUTS.copy()
    # Auxiliary boot data changes execution too. Record the actual supplied
    # bytes without making these files a prerequisite for the MAIN checkpoint.
    for name in ("IRX.DAT", "IOPRP300.IMG", "PAL_NTSC.DAT"):
        path = args.disc_dir / name
        if path.is_file(): result["input_sha256"][name] = file_sha256(path)
    excerpts = args.disc_dir / ".yakuza-disc-ranges"
    if excerpts.is_dir():
        for path in sorted(excerpts.glob("*.ykr")):
            result["input_sha256"][".yakuza-disc-ranges/" + path.name] = file_sha256(path)
    try:
        if args.xvfb:
            require(os.name == "posix", "Xvfb is only for internal Linux execution")
            read_fd, write_fd = os.pipe()
            try:
                with (args.out_dir / "display.log").open("x") as output:
                    server = subprocess.Popen([str(args.xvfb.resolve()), "-displayfd", str(write_fd),
                        "-screen", "0", "640x512x24", "-nolisten", "tcp", "-noreset"],
                        pass_fds=(write_fd,), stdout=output, stderr=subprocess.STDOUT)
                os.close(write_fd); write_fd = -1
                ready, _, _ = select.select([read_fd], [], [], 10)
                require(bool(ready), "Virtual display did not start; inspect display.log")
                display = os.read(read_fd, 100).decode().strip()
                require(display.isdigit(), "Virtual display failed; inspect display.log")
                env["DISPLAY"] = ":" + display
                env["LIBGL_ALWAYS_SOFTWARE"] = "1"
                env["XDG_CACHE_HOME"] = str(args.out_dir.resolve() / "cache")
                env["XDG_CONFIG_HOME"] = str(args.out_dir.resolve() / "config")
            finally:
                os.close(read_fd)
                if write_fd >= 0: os.close(write_fd)
        with (args.out_dir / "boot.log").open("x") as output:
            try:
                command = [str(args.exe.resolve()), str(args.disc_dir.resolve()), str(args.seconds),
                           str(args.out_dir.resolve() / "state")]
                if args.continue_main: command.append("continue")
                run = subprocess.run(command,
                    stdout=output, stderr=subprocess.STDOUT, env=env, timeout=args.seconds + 20)
                result["exit_code"] = run.returncode
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
        log = (args.out_dir / "boot.log").read_text(errors="replace")
        result["firmware_patch_hook_calls"] = log.count("[yakuza-kernel]")
        result["executed_iop_modules"] = log.count("[yakuza-iop] executed transferred module ")
        result["reached_main"] = "verified original MAIN payload at entry 0x22cc40" in log
        (args.out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        print("Trace:", args.out_dir / "boot.log")
        return 0 if result["reached_main"] and result["exit_code"] == 0 else 1
    finally:
        if server is not None:
            server.terminate()
            try: server.wait(timeout=5)
            except subprocess.TimeoutExpired: server.kill(); server.wait()


if __name__ == "__main__": raise SystemExit(main())
