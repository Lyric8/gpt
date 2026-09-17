#!/usr/bin/env node
/** Validate the exact editable catalog; no dependencies and no network. */
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateDatabase } from '../src/engine.mjs';
const path = process.argv[2] ? resolve(process.argv[2]) : fileURLToPath(new URL('../data/recipes.json', import.meta.url));
try {
  const database = JSON.parse(await readFile(path, 'utf8'));
  const result = validateDatabase(database);
  if (!result.ok) {
    console.error(result.errors.join('\n'));
    process.exitCode = 1;
  } else {
    console.log(`VALID ${database.version}: ${database.recipes.length} recipes, ${Object.keys(database.ingredients).length} ingredients, ${Object.keys(database.sources).length} sources`);
  }
} catch (error) {
  console.error(`Catalog validation failed: ${error.message}`);
  process.exitCode = 1;
}
