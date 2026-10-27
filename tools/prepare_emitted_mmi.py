#!/usr/bin/env python3
"""Correct verified inline MMI emissions in private compilation copies."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from prepare_game import require

EMITTER_SHA256 = "1402bdb9f81923a8c91c7fa790399a2563ebc5f7cd0c899b7c29cb7c6bafc5ee"
INSTRUCTION = re.compile(r"^\s*// (0x[0-9a-fA-F]+): (0x[0-9a-fA-F]+)\s+(\S+).*$")


def corrected(data):
    text = data.replace(b"\r\n", b"\n").decode()
    lines = text.splitlines(keepends=True)
    instructions = [(i, INSTRUCTION.match(line)) for i, line in enumerate(lines) if INSTRUCTION.match(line)]
    sites = []
    for index, (line, instruction) in enumerate(instructions):
        mnemonic = instruction.group(3)
        if mnemonic not in ("pexeh", "prot3w"):
            continue
        word = int(instruction.group(2), 16)
        rt, rd = (word >> 16) & 31, (word >> 11) & 31
        require(word & ~((31 << 16) | (31 << 11)) ==
                (0x70000689 if mnemonic == "pexeh" else 0x700007c9),
                "MMI mnemonic and original instruction encoding differ")
        value = f"GPR_VEC(ctx, {rt})"
        if mnemonic == "pexeh":
            expression = f"_mm_shufflelo_epi16(_mm_shufflehi_epi16({value}, _MM_SHUFFLE(2,3,0,1)), _MM_SHUFFLE(2,3,0,1))"
        else:
            expression = f"_mm_shuffle_epi32({value}, _MM_SHUFFLE(0,3,2,1))"
        old = f"SET_GPR_VEC(ctx, {rd}, {expression});"
        new = f"SET_GPR_VEC(ctx, {rd}, PS2_{mnemonic.upper()}({value}));"
        end = instructions[index + 1][0] if index + 1 < len(instructions) else len(lines)
        bodies = [i for i in range(line + 1, end) if lines[i].strip() in (old, new)]
        require(len(bodies) == 1, "Pinned inline MMI expression or registers differ")
        body = bodies[0]
        indent = lines[body][:len(lines[body]) - len(lines[body].lstrip())]
        lines[body] = indent + new + "\n"
        sites.append({"address": instruction.group(1), "word": instruction.group(2),
                      "opcode": mnemonic, "rt": rt, "rd": rd})
    return "".join(lines).encode(), sites


def cmake_path(path):
    value = path.resolve().as_posix()
    require(not any(c in value for c in '\n\r";'), "Unsupported CMake source path")
    return value


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def prepare(sources, output):
    staged = []
    for source in dict.fromkeys(path.resolve() for path in sources):
        original = source.read_bytes()
        fixed, sites = corrected(original)
        if not sites:
            continue
        directory = hashlib.sha256(str(source.parent).encode()).hexdigest()[:16]
        target = output / directory / source.name
        require(target.resolve() != source, "Keep emitted source unchanged")
        staged.append((source, target, original, fixed, sites, cmake_path(source), cmake_path(target)))
    # Validate every source and path before creating compilation copies.
    for _, target, _, fixed, _, _, _ in staged:
        save(target, fixed)
    return staged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-list", type=Path, required=True)
    parser.add_argument("--emitter-source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    emitter = args.emitter_source.read_bytes().replace(b"\r\n", b"\n")
    require(hashlib.sha256(emitter).hexdigest() == EMITTER_SHA256, "Unsupported MMI emitter; reassess")
    project = Path(__file__).resolve().parents[1]
    output = args.out_dir.resolve()
    require(not output.is_relative_to(project), "Keep private emitted code outside the checkout")
    sources = [Path(line) for line in args.source_list.read_text().splitlines() if line]
    require(bool(sources) and len(sources) <= 250000, "Invalid emitted source list")
    staged = prepare(sources, output)
    cmake = "set(YAKUZA_EMITTED_MMI_INPUTS " + " ".join('"' + row[5] + '"' for row in staged) + ")\n"
    cmake += "set(YAKUZA_EMITTED_MMI_OUTPUTS " + " ".join('"' + row[6] + '"' for row in staged) + ")\n"
    save(output / "corrections.cmake", cmake.encode())
    proof = [{"source": row[5], "output": row[6],
              "source_sha256": hashlib.sha256(row[2]).hexdigest(),
              "corrected_sha256": hashlib.sha256(row[3]).hexdigest(),
              "original_instruction_bytes_changed": False, "sites": row[4]} for row in staged]
    save(output / "verification.json", (json.dumps(proof, indent=2) + "\n").encode())
    print(f"Verified inline MMI permutations: {sum(len(row[4]) for row in staged)} sites in {len(staged)} compilation copies")


if __name__ == "__main__":
    main()
