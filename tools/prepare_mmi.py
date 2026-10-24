#!/usr/bin/env python3
"""Correct three lane permutations in a private copy of the pinned MMI macros."""
import argparse
import hashlib
from pathlib import Path

from prepare_game import require

MACROS_SHA256 = "728d13c159be541a6a2f9250310244c6ff7ed6247988db835f05dfd956a8b197"


def adapt_mmi(data):
    data = data.replace(b"\r\n", b"\n")
    require(hashlib.sha256(data).hexdigest() == MACROS_SHA256,
            "Unsupported runtime header: ps2_runtime_macros.h")
    text = data.decode()
    # PEXEH exchanges even halfwords within each 64-bit half; PEXEW exchanges
    # words 0 and 2. PROT3W rotates the low three words and preserves word 3.
    replacements = {
        "#define PS2_PEXEH(rs) _mm_shufflelo_epi16(_mm_shufflehi_epi16(rs, _MM_SHUFFLE(2, 3, 0, 1)), _MM_SHUFFLE(2, 3, 0, 1))":
        "#define PS2_PEXEH(rs) _mm_shufflelo_epi16(_mm_shufflehi_epi16(rs, _MM_SHUFFLE(3, 0, 1, 2)), _MM_SHUFFLE(3, 0, 1, 2))",
        "#define PS2_PEXEW(rs) _mm_shuffle_epi32(rs, _MM_SHUFFLE(2, 3, 0, 1))":
        "#define PS2_PEXEW(rs) _mm_shuffle_epi32(rs, _MM_SHUFFLE(3, 0, 1, 2))",
        "#define PS2_PROT3W(rs) _mm_shuffle_epi32(rs, _MM_SHUFFLE(0, 3, 2, 1))":
        "#define PS2_PROT3W(rs) _mm_shuffle_epi32(rs, _MM_SHUFFLE(3, 0, 2, 1))",
    }
    for old, new in replacements.items():
        require(text.count(old) == 1, "Pinned MMI permutation no longer matches; reassess")
        text = text.replace(old, new)
    return text.encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macros-header", required=True, type=Path)
    parser.add_argument("--out-file", required=True, type=Path)
    args = parser.parse_args()
    source, output = args.macros_header.resolve(), args.out_file.resolve()
    require(not output.is_relative_to(source.parents[2]), "Keep the dependency checkout unchanged")
    data = adapt_mmi(source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.read_bytes() != data:
        output.write_bytes(data)
    print("Prepared private MMI even-element exchanges and three-word rotation")


if __name__ == "__main__":
    main()
