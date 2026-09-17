#!/usr/bin/env python3
"""Build the distributable, offline single HTML using the Python standard library."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def build(output: Path) -> None:
    data = json.loads((ROOT / 'data/recipes.json').read_text(encoding='utf-8'))
    if data.get('schemaVersion') != 2:
        raise ValueError('Unsupported recipe schema; run node --test before publishing.')
    template = (ROOT / 'src/index.template.html').read_text(encoding='utf-8')
    style = (ROOT / 'src/styles.css').read_text(encoding='utf-8')
    engine = (ROOT / 'src/engine.mjs').read_text(encoding='utf-8')
    app = (ROOT / 'src/app.mjs').read_text(encoding='utf-8')
    # Modules intentionally use named exports and one static, single-line import.
    engine = re.sub(r'^export (?=(?:const|function)\b)', '', engine, flags=re.M)
    app, count = re.subn(r"^import \{[^\n]+\} from './engine\.mjs';\s*\n", '', app, flags=re.M)
    if count != 1 or re.search(r'^(?:import|export)\s', engine + '\n' + app, flags=re.M):
        raise ValueError('Module boundary changed: update the packager instead of silently building bad JavaScript.')
    script = "(() => {\n'use strict';\n" + engine + '\n' + app + '\n})();'
    if '</script' in script.lower() or '</style' in style.lower():
        raise ValueError('Unexpected HTML closing tag in executable source.')
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    for char, escaped in [('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026'), ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
        payload = payload.replace(char, escaped)
    for key, value in [('/*__STYLE__*/',style),('/*__DATA__*/',payload),('/*__SCRIPT__*/',script)]:
        if template.count(key) != 1:
            raise ValueError(f'Missing or duplicated template marker: {key}')
        template = template.replace(key, value)
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
    print(f'Built {output} ({output.stat().st_size:,} bytes; {len(data["recipes"])} recipes)')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'index.html')
    args = parser.parse_args()
    build(args.output)
