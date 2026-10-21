#!/usr/bin/env python3
"""Bind private verified overlay translations to the native boot host."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

from overlay_image import SLOT_START, parse_overlay, verify
from prepare_game import require


def fnv(data):
    value = 0xcbf29ce484222325
    for byte in data:
        value = ((value ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return value


def module(folder):
    verify(folder, write_outputs=False)
    layout = json.loads((folder / "layout.json").read_text())
    elf = (folder / "analysis.elf").read_bytes()
    image = elf[0x100:0x100 + layout["file_size"]]
    parsed = asdict(parse_overlay(image))
    require(all(parsed[key] == (tuple(layout[key]) if key == "constructors" else layout[key])
                for key in parsed), "Overlay layout differs from original bytes")
    require(hashlib.sha256(image).hexdigest() == layout["file_sha256"], "Overlay payload SHA-256 differs")
    folder = folder / "generated"
    text = (folder / "register_functions.cpp").read_text()
    fields = {}
    for name in ("Base", "End", "SlotCount"):
        match = re.search(r'g_ps2RecompiledFunctionTable' + name + r' = (0x[0-9a-f]+|[0-9]+)u;', text)
        require(match is not None, "Missing overlay registration bounds")
        fields[name] = int(match[1], 0)
    require(SLOT_START + 64 <= fields["Base"] < fields["End"] <= SLOT_START + len(image) and
            (fields["End"] - fields["Base"]) % 4 == 0 and
            fields["SlotCount"] * 4 == fields["End"] - fields["Base"], "Invalid overlay table bounds")
    pattern = r'g_ps2RecompiledFunctionTable\[(\d+)\] = (\w+); // (0x[0-9a-f]+)'
    entries, symbols = {}, set()
    assignments = re.findall(r'g_ps2RecompiledFunctionTable\[\d+\] = ', text)
    for slot, symbol, address in re.findall(pattern, text):
        slot, address = int(slot), int(address, 16)
        require(re.fullmatch(r'[A-Za-z_]\w*', symbol, re.ASCII) is not None and
                address not in entries and slot < fields["SlotCount"] and
                fields["Base"] + slot * 4 == address and
                SLOT_START + 64 <= address < SLOT_START + len(image), "Invalid overlay dispatch entry")
        require((folder / (symbol + ".cpp")).is_file(), "Missing translated overlay function source")
        entries[address] = symbol
        symbols.add(symbol)
    require(bool(entries) and len(entries) == len(assignments), "Unrecognized overlay registration")
    require(all(not ctor or ctor in entries for ctor in layout["constructors"]),
            "Original overlay constructor has no exact registration")
    return layout, sorted(entries.items()), sorted(folder / (name + ".cpp") for name in symbols), fnv(image)


def write_changed(path, text):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def cmake_path(path):
    value = path.as_posix()
    require(not any(c in value for c in '\n\r;"') and "]==]" not in value,
            "Unsupported character in generated-source path")
    return "[==[" + value + "]==]"


def prepare(folders, output):
    require(not output.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
            "Keep generated overlay bindings outside the checkout")
    modules = [module(folder.resolve()) for folder in folders]
    require(len({item[0]["module_id"] for item in modules}) == len(modules), "Duplicate compiled overlay ID")
    source = '#include "yakuza/boot_overlays.h"\n'
    cmake = 'set(YAKUZA_BOOT_OVERLAY_TARGETS)\n'
    report = []
    for index, (layout, entries, files, fingerprint) in enumerate(modules):
        for symbol in sorted({symbol for _, symbol in entries}):
            source += f'void {symbol}(uint8_t*, R5900Context*, PS2Runtime*);\n'
        source += f'const yakuza::NativeEntry overlay_entries_{index}[] = {{\n'
        source += ''.join(f'    {{0x{address:x}u, {symbol}}},\n' for address, symbol in entries) + '};\n'
        target = f'yakuza_boot_overlay_{index}'
        cmake += f'add_library({target} OBJECT\n'
        cmake += ''.join('    ' + cmake_path(path) + '\n' for path in files) + ')\n'
        cmake += f'target_link_libraries({target} PRIVATE ps2_runtime)\n'
        cmake += f'target_compile_features({target} PRIVATE cxx_std_20)\n'
        cmake += f'target_include_directories({target} PRIVATE {cmake_path(files[0].parent)})\n'
        cmake += f'target_precompile_headers({target} PRIVATE "${{ps2recomp_SOURCE_DIR}}/ps2xRuntime/include/ps2_runtime_macros.h")\n'
        cmake += f'set_target_properties({target} PROPERTIES UNITY_BUILD ON UNITY_BUILD_BATCH_SIZE 16)\n'
        cmake += f'if(WIN32)\n target_compile_definitions({target} PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)\nendif()\n'
        for path in files:
            if path.stat().st_size > 524288:
                cmake += f'set_source_files_properties({cmake_path(path)} PROPERTIES SKIP_UNITY_BUILD_INCLUSION ON)\n'
        cmake += f'list(APPEND YAKUZA_BOOT_OVERLAY_TARGETS {target})\n'
        report.append({"module": layout["name"], "id": layout["module_id"], "sources": len(files),
                       "entries": len(entries), "file_sha256": layout["file_sha256"]})
    source += 'namespace yakuza {\nstd::span<const BootOverlay> compiled_boot_overlays() {\n'
    if modules:
        source += '    static const BootOverlay programs[] = {\n'
        for index, (layout, entries, files, fingerprint) in enumerate(modules):
            source += f'        {{{layout["module_id"]}u, {json.dumps(layout["name"])}, {layout["file_size"]}u, 0x{fingerprint:x}ULL, overlay_entries_{index}}},\n'
        source += '    };\n    return programs;\n'
    else:
        source += '    return {};\n'
    source += '}\n}\n'
    output.mkdir(parents=True, exist_ok=True)
    write_changed(output / 'register_boot_overlays.cpp', source)
    write_changed(output / 'boot_overlays.cmake', cmake)
    write_changed(output / 'boot-overlay-verification.json', json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-dir', type=Path, action='append', default=[])
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.module_dir, args.out_dir)))


if __name__ == '__main__':
    main()
