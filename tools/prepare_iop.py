#!/usr/bin/env python3
"""Prepare a checked private IOP emulator with masked sound DMA deferred."""
from pathlib import Path
import argparse
import hashlib
import json

SOURCE_SHA256 = "01deb410d04f441be12adc68638846061f19759e007c36cdfcbe987796199d36"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iop-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    source_dir = args.iop_dir.resolve()
    output = args.out_dir.resolve()
    project = Path(__file__).resolve().parents[1]
    if output.is_relative_to(project) or output.is_relative_to(source_dir):
        parser.error("Keep adapted IOP output outside both source checkouts")
    data = (source_dir / "src/emulator/iop_emulator.cpp").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        parser.error("Unsupported IOP emulator source; reassess the pinned adaptation")
    old = b"if (servicingDmaInterrupts || pendingDmaInterrupts.empty())"
    if data.count(old) != 1:
        parser.error("Pinned IOP interrupt guard no longer matches")
    new = (b"// Retain due DMA interrupts while the IOP CPU masks interrupts.\n"
           b"            // They become deliverable after the outer critical section restores I_CTRL.\n"
           b"            if (servicingDmaInterrupts || pendingDmaInterrupts.empty() || memory.interruptControl() == 0u)")
    adapted = data.replace(old, new)
    target = output / "iop_emulator.cpp"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_bytes() != adapted:
        target.write_bytes(adapted)
    report = {"source_sha256": SOURCE_SHA256, "adapted_sha256": hashlib.sha256(adapted).hexdigest(),
              "policy": "Retain pending sound DMA interrupts while I_CTRL is disabled"}
    (output / "adaptation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Prepared private IOP interrupt masking adaptation")


if __name__ == "__main__":
    main()
