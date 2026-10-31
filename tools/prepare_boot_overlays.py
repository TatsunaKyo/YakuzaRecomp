#!/usr/bin/env python3
"""Bind private verified overlay translations to the native boot host."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

from overlay_image import SLOT_START, parse_overlay, verify
from prepare_boot_supplement import read_ranges, subtract
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
    # Later private analyses can reuse byte-identical earlier translations.
    # Keep physical paths stable so adding methods does not rebuild/regroup all
    # existing unity batches. Each reused file keeps its own declarations.
    files = [path.resolve(strict=True) for path in sorted(folder / (name + ".cpp") for name in symbols)]
    require(len(set(files)) == len(files), "Overlay symbols alias the same translation source")
    return layout, sorted(entries.items()), files, fnv(image)


def write_changed(path, text):
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def cmake_path(path):
    value = path.as_posix()
    require(not any(c in value for c in '\n\r;"') and "]==]" not in value,
            "Unsupported character in generated-source path")
    return "[==[" + value + "]==]"


def retained_translation(previous_folder, previous, folder, current):
    """Compare verified generations, including aliases rather than just counts."""
    old_layout, old_entries, old_files, _ = previous
    layout, entries, _, _ = current
    require(layout == old_layout, "Updated overlay changed original guest bytes or layout")
    require(not subtract(read_ranges(previous_folder / "decoded.csv"), read_ranges(folder / "decoded.csv")),
            "Updated overlay removed previously decoded instructions")
    current_entries = dict(entries)
    require(all(current_entries.get(address) == symbol for address, symbol in old_entries),
            "Updated overlay removed or replaced a previous callable entry")
    for symbol in sorted({symbol for _, symbol in old_entries}):
        old_source = previous_folder / "generated" / (symbol + ".cpp")
        source = folder / "generated" / (symbol + ".cpp")
        require(source.read_bytes() == old_source.read_bytes(),
                "Updated overlay changed a previous translation source: " + symbol)
    return {"retained_entries": len(old_entries), "retained_sources": len(old_files)}


def prepare(folders, output, previous_folders=()):
    require(not output.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
            "Keep generated overlay bindings outside the checkout")
    folders = [folder.resolve() for folder in folders]
    modules = [module(folder) for folder in folders]
    require(len({item[0]["module_id"] for item in modules}) == len(modules), "Duplicate compiled overlay ID")
    previous_folders = [folder.resolve() for folder in previous_folders]
    previous = [module(folder) for folder in previous_folders]
    require(len({item[0]["module_id"] for item in previous}) == len(previous), "Duplicate baseline overlay ID")
    current_by_id = {item[0]["module_id"]: (folder, item) for folder, item in zip(folders, modules)}
    retention = {}
    for previous_folder, baseline in zip(previous_folders, previous):
        ident = baseline[0]["module_id"]
        require(ident in current_by_id, "Baseline overlay is absent from the current module selection")
        folder, current = current_by_id[ident]
        require(folder != previous_folder, "Overlay baseline must be a separate retained generation")
        retention[ident] = retained_translation(previous_folder, baseline, folder, current)
    source = '#include "yakuza/boot_overlays.h"\n'
    cmake = 'set(YAKUZA_BOOT_OVERLAY_TARGETS)\n'
    # Re-run the comparison if an earlier or current compilation input changes.
    # Physical paths also cover translations reused through symbolic links.
    watched_sources = sorted({path for item in modules + previous for path in item[2]})
    if watched_sources:
        cmake += 'set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS\n'
        cmake += ''.join('    ' + cmake_path(path) + '\n' for path in watched_sources) + ')\n'
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
        cmake += f'target_precompile_headers({target} PRIVATE "${{runtime_private}}/include/ps2_runtime_macros.h")\n'
        cmake += f'set_target_properties({target} PROPERTIES UNITY_BUILD ON UNITY_BUILD_BATCH_SIZE 16)\n'
        cmake += f'if(WIN32)\n target_compile_definitions({target} PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN)\nendif()\n'
        for path in files:
            if path.parent != files[0].parent:
                cmake += (f'set_source_files_properties({cmake_path(path)} PROPERTIES '
                          f'SKIP_UNITY_BUILD_INCLUSION ON SKIP_PRECOMPILE_HEADERS ON '
                          f'INCLUDE_DIRECTORIES {cmake_path(path.parent)})\n')
            elif path.stat().st_size > 524288:
                cmake += f'set_source_files_properties({cmake_path(path)} PROPERTIES SKIP_UNITY_BUILD_INCLUSION ON)\n'
        cmake += f'list(APPEND YAKUZA_BOOT_OVERLAY_TARGETS {target})\n'
        report.append({"module": layout["name"], "id": layout["module_id"], "sources": len(files),
                       "entries": len(entries), "file_sha256": layout["file_sha256"],
                       **retention.get(layout["module_id"], {})})
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
    parser.add_argument('--previous-module-dir', type=Path, action='append', default=[],
                        help='Retained verified generation whose guest bytes, entries and sources must survive')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.module_dir, args.out_dir, args.previous_module_dir)))


if __name__ == '__main__':
    main()
