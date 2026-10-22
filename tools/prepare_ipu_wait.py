#!/usr/bin/env python3
"""Correct the observed PAL IPU wait helper's translated signed branch width.

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


def corrected(data, before=BEFORE, after=AFTER):
    data = data.replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    require(digest in (before, after), "Unsupported generated PAL IPU wait helper; reassess")
    if digest == before:
        require(data.count(OLD.encode()) == 1, "IPU wait branch differs")
        result = data.replace(OLD.encode(), NEW.encode())
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
    data = path.read_bytes()
    fixed = corrected(data)
    original = fixed.replace(NEW.encode(), OLD.encode())
    require(hashlib.sha256(original).hexdigest() == BEFORE, "Original generated helper cannot be recovered")
    write_new(args.out_dir / "generated-originals" / SOURCE, original)
    # All verification and preservation precede the sole native-source edit.
    if data != fixed:
        path.write_bytes(fixed)
    proof = {"source": str(path.resolve()), "branch_pc": "0x12a678", "original_word": "0x06230042",
             "original_generated_sha256": BEFORE, "corrected_generated_sha256": AFTER,
             "signed_test_bits": 64, "original_mips_bytes_changed": False}
    write_new(args.out_dir / "ipu-wait-verification.json", (json.dumps(proof, indent=2) + "\n").encode())
    print("Verified PAL IPU wait: LD/BGEZL tests the full 64-bit result")


if __name__ == "__main__":
    main()
