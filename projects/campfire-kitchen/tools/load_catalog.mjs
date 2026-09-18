/** Build-time loader. Never imported into the browser bundle. */
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
export function loadCatalog(path = fileURLToPath(new URL('../data/recipes.json', import.meta.url))) {
  const input = JSON.parse(readFileSync(path, 'utf8'));
  if (input.catalogSource !== 1) return input;
  const root = resolve(dirname(path), '..');
  const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const text = execFileSync(python, [resolve(root, 'tools/catalog.py'), '--root', root], {
    encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, timeout: 30000,
  });
  return JSON.parse(text);
}
