#!/usr/bin/env python3
"""Prepare private corrections for verified PAL FMAC/VF0 and MAC-flag sites.

Original translations and instruction bytes remain unchanged. Every flag read
in the supported family has a verified intervening wait for the FMAC pipeline.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from prepare_game import require

SOURCES = (
    ('FUN_001898f0_0x1898f0.cpp', '19d3488e952f5bc225b59ad7575eef8c90568ccb8bf6ae2430167500d5f14e0e', 5, 1),
    ('FUN_00189950_0x189950.cpp', 'b2f5c40e6149a2a9177c6a850e65538a3b8a0fd852c572cbf889b8d004b614b0', 6, 1),
    ('FUN_0018a2f0_0x18a2f0.cpp', '915041d45c1bec1e378a73fe2c2737ccb000dcb9599775daa6e138122175f1b2', 9, 2),
    ('FUN_0018a3e0_0x18a3e0.cpp', '06f0211a8577efa1d9c6b529af70a4e65fee761a74578bf28e4a2a68b3da91f0', 9, 2),
    ('FUN_0018a4d0_0x18a4d0.cpp', '9f3e242de6ae516fb675c297d202a36605403390440a476bc07f9461aa782f51', 9, 2),
    ('FUN_0018a610_0x18a610.cpp', '7d017e36adeab0f6e37881470437c169cc0182a0ec5f07d160184063f6bf81c2', 5, 1),
    ('FUN_0018a670_0x18a670.cpp', '36b4a9661811082f488f41f9350585009b1d3731310ce9eb72d75924a39c0ef7', 5, 1),
    ('FUN_0018a6f0_0x18a6f0.cpp', '6e32f48adab6c6f76f4a6676c3ec7a20123977a8a70364d850b036926ae1f568', 8, 2),
    ('FUN_0018a7e0_0x18a7e0.cpp', '7bde667a83c4e8b4517372434f5b2f4ca5e35256fac2e8d855a6e51ee762a4d4', 8, 2),
    ('FUN_0018a8d0_0x18a8d0.cpp', 'b51b3a5334c7fb8a0caad0ac922da4d9dab33464579cb1f93997317ca1e7da2d', 8, 2),
    ('FUN_0033a430_0x33a430.cpp', 'b865f026909ffb491a41f8002f4ce4e92c663084d5d71ece769674c5fb8098c8', 5, 1),
    ('decoded_chunk_001A1660_0x1a1660.cpp', '1b3b038d3d8fe0f32fe5ea132cb99105c72ced94e110661b153227b42e6946af', 3, 1),
    ('decoded_chunk_001A1710_0x1a1710.cpp', '1788f14813719d42ce0eabef93d0b439f39ade16b7f60f719db5964585490c99', 7, 1),
    ('decoded_chunk_001A17D0_0x1a17d0.cpp', '9f473f194906a9fcdcfc304ba090258765b562ae1947318b6909171fbcd0f118', 4, 1),
    ('decoded_chunk_001A18A0_0x1a18a0.cpp', '33c645276aa738bfbf0de2a1db76db2b74a54db693e87716200992495315b8a8', 8, 1),
    ('decoded_chunk_001A1AC0_0x1a1ac0.cpp', 'ef9be334b6a18c2fe29ca5bda04712e4909f750f7836fa1d0f9a57c64a99ee23', 4, 1),
    ('decoded_chunk_001A1CD0_0x1a1cd0.cpp', '97fc5d9856c6b3e58e69da0a962863bda3fad230751d923a02158caaf353659c', 96, 7),
)

FIXTURE_SHA256 = "ba5ca0a0aa0ade21bc8b321e5d1f7ba995884edfee062a22170dea59980324d4"
OLD = "    { __m128 res = PS2_VSUB(ctx->vu0_vf[5], ctx->vu0_vf[4]); __m128i mask = _mm_set_epi32(0, 0, -1, -1); ctx->vu0_vf[0] = PS2_VBLEND(ctx->vu0_vf[0], res, _mm_castsi128_ps(mask)); }"
NEW = "    yakuza::vu0UpperWithFlags(*ctx, runtime->gs(), 0x0184282cu);"
INCLUDE = '#include "ps2_runtime.h"\n'

FMAC = ("vadd", "vsub", "vmul", "vmadd", "vmsub", "vopmula", "vopmsub")
INSTRUCTION = re.compile(r"^\s*// (0x[0-9a-fA-F]+): (0x[0-9a-fA-F]+)\s+(\S+)(.*)$")

def corrected(data, expected, count=1, reads=0):
    data = data.replace(b"\r\n", b"\n")
    require(hashlib.sha256(data).hexdigest() == expected, "Unsupported generated VU0 helper; reassess")
    text = data.decode()
    require(text.count(INCLUDE) == 1, "Generated VU0 include shape differs")
    if expected == FIXTURE_SHA256:
        require(count == 1 and reads == 0 and text.count(OLD) == 1, "Synthetic VSUB shape differs")
        text = text.replace(OLD, NEW)
    else:
        lines = text.splitlines(keepends=True)
        instructions = [(i, INSTRUCTION.match(line)) for i, line in enumerate(lines) if INSTRUCTION.match(line)]
        fixed = 0
        found_reads = 0
        for j, (line, instruction) in enumerate(instructions):
            mnemonic = instruction.group(3)
            if mnemonic.startswith("cfc2") and "$vi17" in instruction.group(4):
                previous = [k for k in range(j) if instructions[k][1].group(3).startswith(FMAC)]
                require(bool(previous), "MAC read has no preceding verified arithmetic")
                gap = [m.group(3) for _, m in instructions[previous[-1] + 1:j]]
                require(len(gap) >= 5 and sum(m in ("vnop", "lqc2") for m in gap) >= 4,
                        "MAC read no longer drains the flag pipeline")
                found_reads += 1
            if not mnemonic.startswith(FMAC):
                continue
            word = int(instruction.group(2), 16)
            require(word & 0xfe000000 == 0x4a000000, "Unexpected original COP2 upper encoding")
            end = instructions[j+1][0] if j+1 < len(instructions) else len(lines)
            bodies = [i for i in range(line+1, end)
                      if re.fullmatch(r"\s*\{ .*\}\s*", lines[i]) and "ctx->vu0_" in lines[i]]
            require(len(bodies) == 1, "Generated FMAC body differs")
            i = bodies[0]
            indent = lines[i][:len(lines[i])-len(lines[i].lstrip())]
            lines[i] = indent + f"yakuza::vu0UpperWithFlags(*ctx, runtime->gs(), 0x{word & 0x01ffffff:08x}u);\n"
            fixed += 1
        require(fixed == count and found_reads == reads, "Verified VU0 family coverage differs")
        text = "".join(lines)
    return text.replace(INCLUDE, INCLUDE + '#include "yakuza/vu0_macro.hpp"\n').encode()

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)

def prepare_batch(sources, output):
    prepared = []
    for source, expected, count, reads in sources:
        require(not source.is_symlink(), "Generated VU0 source must not be a symbolic link")
        data = source.read_bytes()
        fixed = corrected(data, expected, count, reads)
        prepared.append((source, fixed, {"source": str(source.resolve()), "original_generated_sha256": expected,
            "corrected_generated_sha256": hashlib.sha256(fixed).hexdigest(), "FMAC_sites": count,
            "MAC_reads": reads, "flag_waits_verified": True, "original_instruction_bytes_changed": False}))
    # Validate every complete input before writing any source or metadata.
    for source, data, proof in prepared:
        save(output / source.name, data)
    return [proof for _, _, proof in prepared]

def cmake_path(path):
    value = path.resolve().as_posix()
    require(not any(c in value for c in '\n\r";'), "Unsupported character in generated CMake path")
    return value

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    generated, output = args.generated_dir.resolve(), args.out_dir.resolve()
    require(not output.is_relative_to(project) and not output.is_relative_to(generated), "Keep private VU0 output outside source trees")
    present = [(generated / name).is_file() for name, _, _, _ in SOURCES]
    sources = []
    if any(present):
        require(all(present) and not generated.is_relative_to(project), "Incomplete or nonprivate PAL translations")
        sources = [(generated / name, expected, count, reads) for name, expected, count, reads in SOURCES]
    else:
        require((generated / "synthetic_entry.cpp").is_file(), "Missing verified PAL VU0 helpers")
    fixture = project / "tests/fixtures/vu-macro/raw_vsub.cpp"
    # Resolve all CMake strings before outputs too.
    inputs = [cmake_path(source) for source, _, _, _ in sources]
    outputs = [cmake_path(output / source.name) for source, _, _, _ in sources]
    fixture_output = cmake_path(output / fixture.name)
    proofs = prepare_batch(sources + [(fixture, FIXTURE_SHA256, 1, 0)], output)
    cmake = "set(YAKUZA_VU0_INPUTS " + " ".join('"' + p + '"' for p in inputs) + ")\n"
    cmake += "set(YAKUZA_VU0_OUTPUTS " + " ".join('"' + p + '"' for p in outputs) + ")\n"
    cmake += 'set(YAKUZA_VU0_TEST_SOURCE "' + fixture_output + '")\n'
    save(output / "vu0-corrections.cmake", cmake.encode())
    save(output / "verification.json", (json.dumps(proofs, indent=2) + "\n").encode())
    print(f"Prepared {len(sources)} verified PAL VU0 helpers and the original-free regression fixture")

if __name__ == "__main__":
    main()
