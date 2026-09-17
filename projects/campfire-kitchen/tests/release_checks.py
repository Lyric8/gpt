from pathlib import Path
import json,subprocess,sys,hashlib,time,urllib.request,urllib.error,socket
import jsonschema
R=Path(__file__).resolve().parents[1]
checks=[]
def ok(name):checks.append({'name':name,'passed':True});print('PASS',name)
d=json.loads((R/'data/recipes.json').read_text());schema=json.loads((R/'data/recipes.schema.json').read_text())
jsonschema.Draft202012Validator.check_schema(schema);jsonschema.validate(d,schema);ok('JSON Schema v2自身有效且完整50道数据通过结构校验')
subprocess.run(['node','tools/check_catalog.mjs'],cwd=R,check=True);ok('独立CLI语义校验器成功')
before=(R/'index.html').read_bytes();subprocess.run([sys.executable,'tools/build.py'],cwd=R,check=True);assert (R/'index.html').read_bytes()==before;ok('相同源码数据连续构建逐字节一致')
for p in ['src/engine.mjs','src/app.mjs','tools/check_catalog.mjs','tests/engine.test.mjs']:subprocess.run(['node','--check',p],cwd=R,check=True)
ok('全部ES模块与CLI通过Node语法检查')
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
proc=subprocess.Popen([sys.executable,'tools/serve.py','--no-browser','--port',str(port)],cwd=R,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
 response=None
 for _ in range(30):
  try:
   response=urllib.request.urlopen(f'http://127.0.0.1:{port}/index.html',timeout=1);break
  except (OSError,urllib.error.URLError):time.sleep(.1)
 if response is None:raise RuntimeError('Local server did not start')
 assert response.read()==before and response.headers['X-Content-Type-Options']=='nosniff';ok('可选标准库HTTP服务真实返回完整发行HTML及nosniff头')
 try:urllib.request.urlopen(f'http://127.0.0.1:{port}/docs/',timeout=1)
 except urllib.error.HTTPError as e:assert e.code==403
 else:raise AssertionError('directory listing not denied')
 ok('HTTP服务不开放目录列表')
finally:
 proc.terminate()
 try:proc.communicate(timeout=3)
 except subprocess.TimeoutExpired:proc.kill();proc.communicate()
report={'ok':True,'count':len(checks),'checks':checks,'sha256':hashlib.sha256(before).hexdigest(),'bytes':len(before)}
(R/'test-results/release-v2-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
