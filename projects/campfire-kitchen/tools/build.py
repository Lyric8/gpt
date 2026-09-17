#!/usr/bin/env python3
"""Deterministic offline packager for this project's static named ES modules and local CSS.

Each module keeps a separate lexical scope. Cycles, unresolved exports, non-local paths,
unsupported module syntax, bad image metadata and version drift fail the build.
No runtime dependencies, CDN, generated source files, or evaluation of recipe content.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
IMPORT = re.compile(r"^import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]\s*;[ \t]*$", re.M)
EXPORT = re.compile(r'^export\s+(?=(?:async\s+)?function\b|const\b|class\b)((?:async\s+)?(?:function|const|class))\s+([A-Za-z_$][\w$]*)', re.M)
IDENT = re.compile(r'^[A-Za-z_$][\w$]*$')
CSS_IMPORT = re.compile(r"^@import\s+['\"]([^'\"]+)['\"];[ \t]*$", re.M)


def local_path(base: Path, relative: str, boundary: Path) -> Path:
    if not relative.startswith('./') and not relative.startswith('../'):
        raise ValueError(f'Only explicit relative imports are supported: {relative}')
    target = (base / relative).resolve()
    if not target.is_relative_to(boundary.resolve()) or not target.is_file():
        raise ValueError(f'Missing or out-of-bound source: {relative}')
    return target


def bundle_modules(entry: Path, boundary: Path) -> str:
    """Supported contract: named static imports, exported functions/const/classes.

    Exported constants are immutable bindings, not mutable live-export shims. Keep
    one declaration per export. Adding unsupported syntax is a build error, never
    a guessed transformation. See docs/EXTENDING_V3.md.
    """
    names: dict[Path, list[str]] = {}
    active: set[Path] = set()
    chunks: list[str] = []

    def visit(path: Path) -> None:
        path = path.resolve()
        if path in active:
            raise ValueError(f'Cyclic module import: {path.name}')
        if path in names:
            return
        active.add(path)
        text = path.read_text(encoding='utf-8')
        exported = [match.group(2) for match in EXPORT.finditer(text)]
        if len(exported) != len(set(exported)):
            raise ValueError(f'Duplicate exports: {path.name}')
        imports = []
        for match in IMPORT.finditer(text):
            dep = local_path(path.parent, match.group(2), boundary)
            if dep.suffix != '.mjs':
                raise ValueError(f'Expected .mjs module: {dep.name}')
            visit(dep)
            bindings = []
            for binding in match.group(1).split(','):
                if not binding.strip():
                    continue
                parts = re.split(r'\s+as\s+', binding.strip())
                if len(parts) not in (1, 2) or any(not IDENT.fullmatch(p) for p in parts):
                    raise ValueError(f'Invalid named import: {binding}')
                if parts[0] not in names[dep]:
                    raise ValueError(f'{path.name}: {parts[0]} is not exported by {dep.name}')
                bindings.append(':'.join(parts))
            imports.append('const {' + ','.join(bindings) + '} = modules[' + json.dumps(dep.relative_to(boundary).as_posix()) + '];')
        text = IMPORT.sub('', text)
        text = EXPORT.sub(lambda m: m.group(1) + ' ' + m.group(2), text)
        if re.search(r'^\s*(?:import|export)\b', text, re.M) or re.search(r'\bimport\s*\(', text):
            raise ValueError(f'Unsupported module syntax in {path.name}; update the build contract explicitly.')
        key = json.dumps(path.relative_to(boundary).as_posix())
        chunks.append(f'// {path.relative_to(boundary).as_posix()}\nmodules[{key}] = (() => {{\n' + '\n'.join(imports) + '\n' + text + '\nreturn Object.freeze({' + ','.join(exported) + '});\n})();')
        names[path] = exported
        active.remove(path)

    visit(entry)
    return "(() => {\n'use strict';\nconst modules = Object.create(null);\n" + '\n'.join(chunks) + '\n})();'


def bundle_styles(entry: Path, boundary: Path, active: frozenset[Path] = frozenset()) -> str:
    entry = entry.resolve()
    if entry in active:
        raise ValueError('Cyclic CSS import')
    text = entry.read_text(encoding='utf-8')
    text = CSS_IMPORT.sub(lambda m: bundle_styles(local_path(entry.parent, m.group(1), boundary), boundary, active | {entry}), text)
    if re.search(r'@import\b|url\s*\(', text):
        raise ValueError('CSS must be self-contained: unresolved import or URL')
    return text


def webp_dimensions(data: bytes) -> tuple[int, int]:
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP' or int.from_bytes(data[4:8], 'little') + 8 != len(data):
        raise ValueError('Invalid WebP container')
    offset = 12
    while offset + 8 <= len(data):
        kind, size = data[offset:offset+4], int.from_bytes(data[offset+4:offset+8], 'little')
        payload = data[offset+8:offset+8+size]
        if len(payload) != size:
            raise ValueError('Truncated WebP chunk')
        if kind == b'VP8X' and len(payload) >= 10:
            return int.from_bytes(payload[4:7], 'little') + 1, int.from_bytes(payload[7:10], 'little') + 1
        if kind == b'VP8 ' and len(payload) >= 10 and payload[3:6] == b'\x9d\x01\x2a':
            return int.from_bytes(payload[6:8], 'little') & 0x3fff, int.from_bytes(payload[8:10], 'little') & 0x3fff
        if kind == b'VP8L' and len(payload) >= 5 and payload[0] == 0x2f:
            bits = int.from_bytes(payload[1:5], 'little')
            return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
        offset += 8 + size + (size & 1)
    raise ValueError('WebP dimensions not found')


def photo_payload(data: dict) -> dict:
    metadata = json.loads((ROOT / 'data/photos.json').read_text(encoding='utf-8'))
    ids = {r['id'] for r in data['recipes']}
    if set(metadata) != ids:
        raise ValueError(f'Photo coverage mismatch: {sorted(ids ^ set(metadata))}')
    photos = {}
    boundary = (ROOT / 'assets/photos').resolve()
    for key, photo in metadata.items():
        if any(not isinstance(photo.get(field), str) or not photo[field].strip() for field in ('src', 'alt', 'author', 'source', 'license', 'licenseUrl', 'note')):
            raise ValueError(f'Incomplete photo attribution: {key}')
        if not photo['source'].startswith('https://') or not photo['licenseUrl'].startswith('https://'):
            raise ValueError(f'Photo attribution must use HTTPS: {key}')
        path = (ROOT / photo['src']).resolve()
        if not path.is_relative_to(boundary) or path.suffix != '.webp' or not path.is_file():
            raise ValueError(f'Missing or invalid local photo: {key}')
        binary = path.read_bytes()
        if len(binary) > 2_000_000:
            raise ValueError(f'Photo exceeds 2 MB budget: {key}')
        width, height = webp_dimensions(binary)
        if not 1 <= width <= 4096 or not 1 <= height <= 4096:
            raise ValueError(f'Unreasonable photo dimensions: {key}')
        photos[key] = {**photo, 'width': width, 'height': height, 'src': 'data:image/webp;base64,' + base64.b64encode(binary).decode('ascii')}
    return photos


def safe_json(value: object) -> str:
    result = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    for char, escaped in [('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026'), ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
        result = result.replace(char, escaped)
    return result


def build(output: Path) -> None:
    data = json.loads((ROOT / 'data/recipes.json').read_text(encoding='utf-8'))
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    equipment = json.loads((ROOT / 'data/equipment.json').read_text(encoding='utf-8'))
    if data.get('schemaVersion') != 2 or data.get('version') != package['version']:
        raise ValueError('Recipe schema or release version mismatch')
    if equipment.get('schemaVersion') != 1:
        raise ValueError('Unsupported equipment schema')
    template = (ROOT / 'src/index.template.html').read_text(encoding='utf-8')
    style = bundle_styles(ROOT / 'src/styles.css', ROOT / 'src')
    script = bundle_modules(ROOT / 'src/app.mjs', ROOT / 'src')
    if '</script' in script.lower() or '</style' in style.lower():
        raise ValueError('Unexpected closing tag in executable source')
    payloads = {'STYLE': style, 'DATA': safe_json(data), 'EQUIPMENT': safe_json(equipment), 'PHOTOS': safe_json(photo_payload(data)), 'SCRIPT': script}
    for key, value in payloads.items():
        marker = f'/*__{key}__*/'
        if template.count(marker) != 1:
            raise ValueError(f'Missing or duplicated template marker: {marker}')
        template = template.replace(marker, value)
    if re.search(r'/\*__[A-Z]+__\*/', template):
        raise ValueError('Unresolved template placeholder')
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.campfire-', suffix='.tmp', dir=output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(template)
        os.replace(name, output)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(f'Built {output} ({output.stat().st_size:,} bytes; {len(data["recipes"])} recipes and photos)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'index.html')
    build(parser.parse_args().output)
