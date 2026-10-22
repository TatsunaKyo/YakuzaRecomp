#!/usr/bin/env python3
"""Correct the observed PAL IPU wait helpers' translated signed branch width.

The original LD/BGEZL tests bit 63 of IPU_CMD, including BUSY. The pinned
translator emits GPR_S32 there. No original MIPS instruction is changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
from prepare_game import require, write_new

SOURCE = "FUN_0012a638_0x12a638.cpp"
BEFORE = "159ffb3c230549e49f806b8ce39584097d54cca2cda2ffbd83f8acfc876ab680"
AFTER = "8fe3b729c5f7c22f5e15eef687f63f2360110957cc59b71a822e65a4f5edef39"
OLD = "const bool branch_taken_0x12a678 = (GPR_S32(ctx, 17) >= 0);"
NEW = OLD.replace("GPR_S32", "GPR_S64")
TOP_OLD = "const bool branch_taken_0x129644 = (GPR_S32(ctx, 4) >= 0);"
TOP_HELPER = ("FUN_00129508_0x129508.cpp",
              "c6eba761bb7daac36aeb16bd98cbf266eea48853a8a9a91b33dce25cce5fc2c0",
              "9bdf084e5dbae86f568bec52080d9803d099ecee04aff33e451f6b6365c005cc",
              TOP_OLD, TOP_OLD.replace("GPR_S32", "GPR_S64"),
              "0x129644", "0x0481000c", "ipu-top-wait-verification.json")


def corrected(data, before=BEFORE, after=AFTER, old=OLD, new=NEW):
    data = data.replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    require(digest in (before, after), "Unsupported generated PAL IPU wait helper; reassess")
    if digest == before:
        require(data.count(old.encode()) == 1, "IPU wait branch differs")
        result = data.replace(old.encode(), new.encode())
    else:
        result = data
    require(hashlib.sha256(result).hexdigest() == after, "IPU wait correction differs")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = args.generated_dir / SOURCE
    if not path.exists() and (args.generated_dir / "synthetic_entry.cpp").is_file():
        print("Synthetic host: original PAL IPU wait helper is absent")
        return
    require(not args.generated_dir.resolve().is_relative_to(root), "Keep translated originals outside the checkout")
    require(not args.out_dir.resolve().is_relative_to(root), "Keep generated proofs outside the checkout")
    require(not path.is_symlink(), "Generated IPU helper must not be a symbolic link")
    helpers = [(SOURCE, BEFORE, AFTER, OLD, NEW, "0x12a678", "0x06230042", "ipu-wait-verification.json"),
               TOP_HELPER]
    prepared = []
    for name, before, after, old, new, pc, word, proof_name in helpers:
        helper = args.generated_dir / name
        require(not helper.is_symlink(), "Generated IPU helper must not be a symbolic link")
        data = helper.read_bytes()
        fixed = corrected(data, before, after, old, new)
        original = fixed.replace(new.encode(), old.encode())
        require(hashlib.sha256(original).hexdigest() == before, "Original generated helper cannot be recovered")
        prepared.append((helper, data, fixed, original, before, after, pc, word, proof_name))
    # Validate both complete sources before preserving or editing either one.
    for helper, data, fixed, original, before, after, pc, word, proof_name in prepared:
        write_new(args.out_dir / "generated-originals" / helper.name, original)
        if data != fixed:
            helper.write_bytes(fixed)
        proof = {"source": str(helper.resolve()), "branch_pc": pc, "original_word": word,
                 "original_generated_sha256": before, "corrected_generated_sha256": after,
                 "signed_test_bits": 64, "original_mips_bytes_changed": False}
        write_new(args.out_dir / proof_name, (json.dumps(proof, indent=2) + "\n").encode())
    print("Verified PAL IPU waits: CMD and TOP sign tests use the full 64-bit result")


if __name__ == "__main__":
    main()
