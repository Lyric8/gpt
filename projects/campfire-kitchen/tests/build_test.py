"""Build-boundary regression tests: run `python -m unittest discover -s tests -p '*_test.py'`."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('campfire_build',ROOT/'tools/build.py')
build=importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def source(self,name,text):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding='utf-8');return path
    def test_named_import_alias_and_independent_module_scope(self):
        self.source('one.mjs','const privateValue=2;\nexport const answer=privateValue+1;')
        entry=self.source('app.mjs',"import { answer as count } from './one.mjs';\nconst privateValue=9;\nconsole.log(count+privateValue);")
        result=subprocess.run(['node','-e',build.bundle_modules(entry,self.root)],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.strip(),'12')
    def test_cycle_fails(self):
        a=self.source('a.mjs',"import { b } from './b.mjs';\nexport const a=1;")
        self.source('b.mjs',"import { a } from './a.mjs';\nexport const b=1;")
        with self.assertRaisesRegex(ValueError,'Cyclic'):build.bundle_modules(a,self.root)
    def test_missing_export_fails(self):
        self.source('b.mjs','export const other=1;')
        a=self.source('a.mjs',"import { missing } from './b.mjs';")
        with self.assertRaisesRegex(ValueError,'not exported'):build.bundle_modules(a,self.root)
    def test_dynamic_default_and_reexports_fail(self):
        for text in ['export default 1;',"const x=import('./b.mjs');","export { x } from './b.mjs';"]:
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'Unsupported'):
                build.bundle_modules(self.source('a.mjs',text),self.root)
    def test_source_path_boundary(self):
        self.source('outside.mjs','export const x=1;')
        folder=self.root/'safe';folder.mkdir()
        entry=self.source('safe/a.mjs',"import { x } from '../outside.mjs';")
        with self.assertRaisesRegex(ValueError,'out-of-bound'):build.bundle_modules(entry,folder)
    def test_external_module_fails(self):
        entry=self.source('a.mjs',"import { x } from 'https://example.invalid/x.mjs';")
        with self.assertRaisesRegex(ValueError,'relative'):build.bundle_modules(entry,self.root)
    def test_css_order_and_cycle(self):
        entry=self.source('main.css',"@import './base.css';\nbody { margin:0 }")
        self.source('base.css',':root { --gap:1px }')
        self.assertLess(build.bundle_styles(entry,self.root).index(':root'),build.bundle_styles(entry,self.root).index('body'))
        self.source('base.css',"@import './main.css';")
        with self.assertRaisesRegex(ValueError,'Cyclic'):build.bundle_styles(entry,self.root)
    def test_external_css_and_urls_rejected(self):
        for text in ["@import 'https://example.invalid/a.css';",'body { background:url(a.png) }']:
            with self.subTest(text=text),self.assertRaises(ValueError):build.bundle_styles(self.source('main.css',text),self.root)
    def test_json_cannot_close_script_and_roundtrips(self):
        value={'text':'</script><script>alert(1)</script>&\u2028\u2029'}
        encoded=build.safe_json(value)
        self.assertNotIn('<',encoded);self.assertNotIn('&',encoded)
        self.assertEqual(json.loads(encoded),value)
    def test_webp_dimensions_and_corruption(self):
        for path in (ROOT/'assets/photos').glob('*.webp'):
            data=path.read_bytes();width,height=build.webp_dimensions(data)
            self.assertTrue(1<=width<=4096 and 1<=height<=4096)
            with self.assertRaises(ValueError):build.webp_dimensions(data[:-1])
        with self.assertRaises(ValueError):build.webp_dimensions(b'not an image')
    def test_webp_declared_truncated_chunk(self):
        body=b'WEBPVP8 '+struct.pack('<I',100)+b'abc'
        with self.assertRaisesRegex(ValueError,'Truncated'):build.webp_dimensions(b'RIFF'+struct.pack('<I',len(body))+body)
    def test_photos_have_exact_recipe_coverage_and_credit(self):
        data=json.loads((ROOT/'data/recipes.json').read_text())
        payload=build.photo_payload(data)
        self.assertEqual(set(payload),{r['id'] for r in data['recipes']})
        for photo in payload.values():
            self.assertTrue(photo['src'].startswith('data:image/webp;base64,'))
            self.assertTrue(photo['source'].startswith('https://'))
            self.assertTrue(photo['licenseUrl'].startswith('https://'))
            self.assertTrue(photo['author'])
        data['recipes']=data['recipes'][:-1]
        with self.assertRaisesRegex(ValueError,'coverage'):build.photo_payload(data)
    def test_real_build_reproducible_and_bounded(self):
        one=self.root/'one.html';two=self.root/'two.html'
        with contextlib.redirect_stdout(io.StringIO()):build.build(one);build.build(two)
        self.assertEqual(one.read_bytes(),two.read_bytes())
        self.assertLess(one.stat().st_size,5_000_000)
        self.assertNotIn(b'/*__',one.read_bytes())
    def test_version_mismatch_does_not_overwrite_existing_output(self):
        self.source('data/recipes.json','{"schemaVersion":2,"version":"2.0.0"}')
        self.source('package.json','{"version":"3.0.0"}')
        self.source('data/equipment.json','{"schemaVersion":1}')
        out=self.source('keep.html','existing release')
        with patch.object(build,'ROOT',self.root),self.assertRaisesRegex(ValueError,'version'):
            build.build(out)
        self.assertEqual(out.read_text(),'existing release')

if __name__=='__main__':unittest.main()
