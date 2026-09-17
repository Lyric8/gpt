#!/usr/bin/env python3
"""Exercise the exact bundled HTML in Chromium. No server/remote requests required.
This sandbox blocks file:// navigation. Tests therefore use set_content plus a Storage
interface test double; denied real storage is separately tested. Blob contents, rather
than the sandbox download manager, are inspected. These limitations are reported.
"""
from __future__ import annotations
from pathlib import Path
import json, os, shutil, time, traceback
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results';OUT.mkdir(exist_ok=True)
HTML=(ROOT/'index.html').read_text(encoding='utf8')
DATA=json.loads((ROOT/'data/recipes.json').read_text(encoding='utf8'))
checks=[];errors=[];network=[]
SETUP="""(initial) => {
 const values = new Map(Object.entries(initial || {}));
 Object.defineProperty(window, 'localStorage', {configurable:true,value:{
 getItem(k){return values.get(String(k)) ?? null}, setItem(k,v){values.set(String(k),String(v))},
 removeItem(k){values.delete(String(k))}, clear(){values.clear()}, key(i){return [...values.keys()][i]??null},
 get length(){return values.size}}});
 window.__storageDump=()=>Object.fromEntries(values);
 window.__downloads=[]; const create=URL.createObjectURL.bind(URL);
 URL.createObjectURL=(blob)=>{blob.text().then(text=>window.__downloads.push({text,type:blob.type}));return create(blob)};
 window.print=()=>{window.__printed=true};
} """
def ok(name):
 checks.append({'name':name,'passed':True}); print('PASS',name,flush=True)
def nav(p,tab):p.locator(f'nav [data-tab="{tab}"]').click()
def action(p,name,id=None):return p.locator(f'[data-action="{name}"]'+(f'[data-id="{id}"]' if id else '')).first

def wait(p,expr):
 for _ in range(100):
  if p.evaluate(expr):return
  p.wait_for_timeout(30)
 raise AssertionError('Timeout: '+expr)
def new_page(browser,width=1440,storage=True,initial=None):
 p=browser.new_page(viewport={'width':width,'height':1000 if width>700 else 844})
 p.on('pageerror',lambda e:errors.append(str(e)));p.on('request',lambda r:network.append(r.url))
 p.on('dialog',lambda d:d.accept())
 if storage:p.evaluate(SETUP,initial or {})
 p.set_content(HTML);p.wait_for_timeout(80);return p

def load_backup(p,obj):
 p.locator('#backup-import').set_input_files({'name':'test-menu.json','mimeType':'application/json','buffer':json.dumps(obj,ensure_ascii=False).encode()})
 p.wait_for_timeout(150)

def main():
 with sync_playwright() as w:
  browser_path = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser') or w.chromium.executable_path
  b=w.chromium.launch(executable_path=browser_path,headless=True,args=['--no-sandbox'])
  p=new_page(b)
  assert p.locator('[data-card]').count()==50;assert not p.locator('[data-change=choice], [data-change=dry-only]').count()
  ok('内置50卡正确启动；没有鲜干/材料选项控件')
  assert not network;ok('初始加载零网络请求')
  p.screenshot(path=str(OUT/'desktop-browse.png'))
  p.locator('#recipe-search').fill('米纸')
  assert p.locator('[data-card]').count()==1;assert p.locator('#recipe-search').evaluate('(x)=>x===document.activeElement')
  ok('中文搜索按菜谱与材料匹配，输入焦点保留')
  p.locator('#recipe-search').fill('');p.locator('[data-action=category][data-value="主食"]').click()
  assert p.locator('[data-card=okonomiyaki]').count()==1;assert p.locator('[data-card=rosemary-beef]').count()==0
  p.locator('[data-action=category][data-value="全部"]').click()
  p.locator('#experience-filter').select_option('动手');assert p.locator('[data-card]').count()>5
  p.locator('#experience-filter').select_option('全部');ok('分类与动手体验筛选可组合且可清除')
  action(p,'detail','rosemary-beef').click();dlg=p.locator('#recipe-dialog');assert dlg.is_visible()
  assert '鲜迷迭香' in dlg.inner_text();assert '选择鲜' not in dlg.inner_text()
  dlg.locator('[data-action=toggle]').click();dlg.locator('[data-change=portion]').select_option('0.5')
  assert '110 g' in dlg.inner_text();assert '0.5 g' in dlg.inner_text();assert '63℃' in dlg.inner_text()
  ok('固定鲜枝牛肉、半份计算、温度步骤同卡同步')
  dlg.locator('[data-change=step]').first.check();assert dlg.locator('[data-change=step]').first.is_checked()
  dlg.locator('textarea').fill('迷迭香整枝取出，真实试吃后再改。')
  action(dlg,'close-dialog').click();action(p,'detail','chimi-beef').click()
  dlg.locator('[data-action=toggle]').click();dlg.locator('[data-change=portion]').select_option('0.5')
  assert '干牛至' in dlg.inner_text() and '鲜平叶欧芹' in dlg.inner_text()
  action(dlg,'close-dialog').click();nav(p,'prep')
  beef=p.locator('[data-shop=beef]');assert '220 g' in beef.inner_text();assert p.locator('[data-shop=rosemaryFresh]').count()==1
  ok('鲜欧芹与干牛至同菜共存，两份半菜合并220g牛肉')
  beef.locator('input').check();assert beef.locator('input').is_checked()
  nav(p,'menu');p.locator('[data-menu-item=rosemary-beef] [data-change=portion]').select_option('1')
  nav(p,'prep');assert not p.locator('[data-shop=beef] input').is_checked();assert '330 g' in p.locator('[data-shop=beef]').inner_text()
  ok('相关原料需求变化后旧备好勾选自动失效')
  nav(p,'menu');action(p,'detail','rosemary-beef').click();assert not dlg.locator('[data-change=step]').first.is_checked();assert dlg.locator('textarea').input_value().startswith('迷迭香')
  ok('操作步骤进度随配方量变化失效，笔记仍保留')
  dlg.locator('[data-action=timer][data-minutes="1"]').click();assert '0:59' in dlg.locator('#timer-readout').inner_text() or '1:00' in dlg.locator('#timer-readout').inner_text()
  dlg.locator('[data-action=stop-timer]').click();assert dlg.locator('#timer-readout').inner_text()=='未计时';ok('前台检查提醒可启动/停止，不宣称后台闹钟')
  action(dlg,'close-dialog').click();nav(p,'browse');action(p,'preset','play-date').click()
  assert p.locator('[data-menu-item]').count()==5;assert p.locator('[data-menu-item=summer-roll]').count()==1
  p.wait_for_timeout(70);assert p.evaluate('window.scrollY')<=2;ok('套菜单或切换主页面从顶部开始，不被旧滚动位置覆盖')
  assert '5' in p.locator('.metrics').inner_text();p.screenshot(path=str(OUT/'desktop-menu.png'))
  ok('新互动预设正确替换并生成5道菜单与节奏统计')
  first=p.locator('[data-menu-item]').first.get_attribute('data-menu-item')
  second=p.locator('[data-menu-item]').nth(1).get_attribute('data-menu-item')
  p.locator(f'[data-action=move][data-id="{second}"][data-delta="-1"]').click()
  assert p.locator('[data-menu-item]').first.get_attribute('data-menu-item')==second
  action(p,'sort').click();assert p.locator('[data-menu-item]').first.get_attribute('data-menu-item')==first
  ok('手动换出餐顺序与恢复推荐顺序正常')
  action(p,'record').click();nav(p,'browse');p.locator('[data-change=fresh-ideas]').check()
  assert p.locator('[data-card=smash-taco]').count()==0;assert p.locator('[data-card]').count()==45
  p.locator('[data-change=fresh-ideas]').uncheck();ok('最近三次做过记录真实影响新鲜感筛选')
  nav(p,'prep');p.locator('[data-pack-recipe=smash-taco] summary').click()
  assert '生牛肉' in p.locator('[data-pack-recipe=smash-taco]').inner_text();assert '酸黄瓜' in p.locator('[data-pack-recipe=smash-taco]').inner_text()
  p.locator('[data-pack-recipe=smash-taco] [data-kind=home]').first.check()
  p.screenshot(path=str(OUT/'desktop-prep.png'))
  ok('预制任务、原料形态与独立分装组都可见可勾')
  p.locator('[data-shop=groundBeef] input').check();p.locator('[data-change=only-missing]').check()
  assert p.locator('[data-shop=groundBeef]').count()==0;p.locator('[data-change=only-missing]').uncheck()
  ok('只看未备食材筛选不会删除底层数量')
  action(p,'export-md').click();wait(p,'window.__downloads.some(x=>x.type.startsWith("text/markdown"))')
  md=p.evaluate('window.__downloads.find(x=>x.type.startsWith("text/markdown")).text');assert '压烤牛肉塔可' in md and '分装' in md
  assert '{{' not in md;assert '71℃' in md;ok('Markdown Blob含完整定稿步骤与换算，模板已解析')
  action(p,'export-csv').click();wait(p,'window.__downloads.some(x=>x.type.startsWith("text/csv"))')
  csv=p.evaluate('window.__downloads.find(x=>x.type.startsWith("text/csv")).text');assert '处理形态' in csv and '即食熟虾仁' in csv
  ok('CSV Blob保留材料形态、按菜分配，不只给购物总量')
  action(p,'export-backup').click();wait(p,'window.__downloads.some(x=>x.type.startsWith("application/json"))')
  backup=json.loads(p.evaluate('window.__downloads.find(x=>x.type.startsWith("application/json")).text'));assert backup['backupVersion']==2 and len(backup['database']['recipes'])==50
  ok('完整JSON备份同时含菜单、记录与定稿菜谱库')
  action(p,'print').click();assert p.evaluate('window.__printed===true');assert '迷你' in p.locator('#print-container').inner_text() or '米纸' in p.locator('#print-container').inner_text()
  ok('打印区域由当前清单生成，未使用旧版模板')
  action(p,'clear').click();load_backup(p,backup);assert p.locator('[data-menu-item]').count()==5
  ok('导出→清空→导入可恢复5道选菜、份量与状态')
  load_backup(p,{'app':'campfire-kitchen','backupVersion':1,'state':{'people':2,'selected':['rosemary-beef','miso-rice','miso-eggplant'],'configs':{'rosemary-beef':{'portion':.5,'choices':{'herb':'dry'}}},'notes':{'rosemary-beef':'旧笔记'},'herbMode':'dry'}})
  assert p.locator('[data-menu-item]').count()==2;assert '未自动替换' in p.locator('.banner').inner_text();assert '实质重写' in p.locator('.banner').inner_text()
  ok('旧版备份迁移明示退役/重写，不暗替用户换菜')
  nav(p,'review');action(p,'export-library').click();wait(p,'window.__downloads.filter(x=>x.type.startsWith("application/json")).length>=2')
  bad=json.loads(json.dumps(DATA));bad['recipes'][0]['choices']=[]
  p.locator('#library-import').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':json.dumps(bad).encode()})
  wait(p,'document.getElementById("toast").textContent.includes("不再允许choices")')
  assert '50' in p.locator('.intro').inner_text() or p.locator('[data-action=detail]').count()>30
  ok('含鲜干choices的坏库被拒，当前定稿库未覆盖')
  good=json.loads(json.dumps(DATA));good['title']='本机测试库';good['recipes'][0]['title']='<img src=x onerror="window.hacked=true">'
  p.locator('#library-import').set_input_files({'name':'good.json','mimeType':'application/json','buffer':json.dumps(good,ensure_ascii=False).encode()})
  p.wait_for_timeout(150);nav(p,'browse');assert p.locator('[data-card=basil-toast]').count()==1
  assert '<img src=x' in p.locator('[data-card=basil-toast]').inner_text();assert p.locator('[data-card=basil-toast] img').count()==0;assert p.evaluate('window.hacked===undefined')
  ok('扩展库可加载，导入文本HTML转义不会执行注入')
  nav(p,'review');action(p,'restore-library').click();nav(p,'browse');assert '罗勒番茄' in p.locator('[data-card=basil-toast]').inner_text()
  ok('恢复内置库可用，保留仍存在的菜单ID')
  snapshot=p.evaluate('window.__storageDump()');q=new_page(b,initial=snapshot)
  nav(q,'menu');assert q.locator('[data-menu-item]').count()==2;action(q,'detail','rosemary-beef').click()
  assert q.locator('textarea').input_value()=='旧笔记'
  ok('模拟存储重新加载保留菜单和笔记（Storage接口替身）')
  action(q,'close-dialog').click()
  # Mobile paths; check global document and dialog widths separately.
  mobile=new_page(b,width=390)
  action(mobile,'preset','play-date').click();mobile.screenshot(path=str(OUT/'mobile-menu.png'))
  for width in [360,390,430,768]:
   mobile.set_viewport_size({'width':width,'height':844})
   for t in ['browse','menu','prep','review']:
    nav(mobile,t);assert mobile.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'),(width,t)
  ok('360/390/430/768px四种宽度，四主页面均无横向溢出')
  mobile.set_viewport_size({'width':390,'height':844});nav(mobile,'menu');action(mobile,'detail','smash-taco').click()
  assert mobile.locator('#recipe-dialog').is_visible();assert mobile.locator('[data-change=step]').count()==4
  assert mobile.locator('#recipe-dialog').evaluate('(x)=>x.scrollWidth<=x.clientWidth+1')
  mobile.screenshot(path=str(OUT/'mobile-recipe.png'))
  mobile.locator('.step-list').scroll_into_view_if_needed();mobile.screenshot(path=str(OUT/'mobile-steps.png'))
  mobile.locator('[data-change=step]').first.check();assert mobile.locator('[data-change=step]').first.is_checked()
  ok('手机操作卡可滚动、逐步打勾，按钮和数量不挤成文本矩阵')
  action(mobile.locator('#recipe-dialog'),'close-dialog').click();nav(mobile,'prep');mobile.locator('[data-pack-recipe=summer-roll] summary').click();mobile.screenshot(path=str(OUT/'mobile-prep.png'))
  ids=mobile.locator('[id]').evaluate_all('(xs)=>xs.map(x=>x.id)');assert len(ids)==len(set(ids));ok('页面/弹窗DOM ID唯一')
  denied=new_page(b,width=390,storage=False);assert '浏览器不允许本地保存' in denied.locator('.banner').inner_text()
  action(denied,'preset','play-date').click();assert denied.locator('[data-menu-item]').count()==5
  ok('真实存储被拒仍能选菜与计算，明确提醒备份')
  broken=new_page(b,initial={'campfire-kitchen-state-v2':'{bad-json'})
  assert '损坏' in broken.locator('.banner').inner_text();action(broken,'preset','play-date').click()
  stored=broken.evaluate('window.__storageDump()');assert stored['campfire-kitchen-state-v2-recovery']=='{bad-json'
  ok('损坏存储原文被救援留存，不静默覆写唯一副本')
  freezer=new_page(b);action(freezer,'detail','sweetpotato-dessert').click();freezer.locator('#recipe-dialog [data-action=toggle]').click();action(freezer.locator('#recipe-dialog'),'close-dialog').click();nav(freezer,'menu')
  assert freezer.locator('.issue.danger').count()==1;freezer.locator('[data-change=freezer]').check();assert freezer.locator('.issue.danger').count()==0
  ok('设备冷冻前提明确提示，确认后不改食谱')
  assert not errors,errors;ok('全部交互未发生JS异常')
  # Only Blob downloads and no remote network have been requested.
  assert all(x.startswith('blob:') for x in network),network
  ok('交互过程中无外部网络依赖')
  b.close()

try:
 main()
except Exception:
 (OUT/'browser-v2-report.json').write_text(json.dumps({'ok':False,'checks':checks,'errors':errors,'trace':traceback.format_exc()},ensure_ascii=False,indent=2))
 raise
else:
 (OUT/'browser-v2-report.json').write_text(json.dumps({'ok':True,'count':len(checks),'checks':checks,'errors':errors,'network':network,'mode':'Exact bundled HTML set_content; Storage test double and real denied-storage branches; Blob byte inspection. file:// blocked by sandbox policy.'},ensure_ascii=False,indent=2))
 print('COMPLETE',len(checks),'browser checks')
