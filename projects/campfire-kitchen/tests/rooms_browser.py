#!/usr/bin/env python3
"""Real HTTP, cookies and localStorage acceptance. Never falls back to simulated origins.

The adjustable clock belongs exclusively to this test's in-process Store; production
has no clock/expiry override endpoint. GitHub delivery itself is covered by unit transport
fixtures plus the deployment archive-probe. This test never writes real room archives.
"""
from __future__ import annotations
import hashlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path
import httpx
import uvicorn
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.serve_rooms import preview_app
from server.rooms.domain import WEEK

OUT=ROOT/'test-results';OUT.mkdir(exist_ok=True)
checks=[];errors=[];external=[]
def ok(name):
    checks.append(name);print('PASS',name,flush=True)
def action(page,name,value=None):
    return page.locator(f'[data-room-action="{name}"]'+(f'[data-value="{value}"]' if value is not None else ''))
def synced(page):
    expect(page.locator('.room-sync.synced')).to_be_visible(timeout=30000)
def pane(page,value):
    action(page,'pane',value).click()
def vote(page,key):
    return page.locator(f'[data-room-action="vote"][data-id="{key}"]')
def wait_for(predicate,page,timeout=12):
    until=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>until:raise AssertionError('State convergence timed out')
        page.wait_for_timeout(100)
def entry(page,number,nickname,pin='246810',create=False):
    action(page,'mode','create' if create else 'join').click()
    page.locator('#room-number').fill(number)
    page.locator('#room-nickname').fill(nickname)
    page.locator('#room-passcode').fill(pin)
    page.locator('#room-entry-form button[type=submit]').click()


def run():
    clock=[time.time()]
    with tempfile.TemporaryDirectory() as tmp:
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        app,store=preview_app(Path(tmp)/'rooms.db',origin,lambda:clock[0])
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,proxy_headers=False))
        thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            assert server.started
            with httpx.Client(base_url=origin) as http:
                response=http.get('/');assert response.status_code==200
                assert response.content==(ROOT/'index.html').read_bytes()
                assert http.get('/api/rooms/health').json()['protocol']==1
            ok('HTTP serves exact compiled HTML and room API')
            with sync_playwright() as pw:
                launch={'headless':True}
                if os.getenv('CHROMIUM_PATH'):launch['executable_path']=os.environ['CHROMIUM_PATH']
                browser=pw.chromium.launch(**launch)
                def page(context):
                    p=context.new_page();p.set_default_timeout(12000)
                    p.on('pageerror',lambda error:errors.append(str(error)))
                    p.on('request',lambda request:external.append(request.url) if request.url.startswith(('http:','https:')) and not request.url.startswith(origin+'/') else None)
                    p.on('dialog',lambda dialog:dialog.accept())
                    return p
                host_context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Asia/Shanghai')
                guest_context=browser.new_context(viewport={'width':390,'height':844},timezone_id='Asia/Shanghai')
                host=page(host_context);guest=page(guest_context)
                host.goto(origin+'/#rooms');host.screenshot(path=str(OUT/'rooms-lobby-desktop.png'),full_page=True)
                entry(host,'004321','小明',create=True);expect(host.locator('.room-number')).to_have_text('004321');synced(host)
                cookie=next(c for c in host_context.cookies() if c['name']=='campfire-device-dev')
                assert cookie['httpOnly'] and cookie['sameSite']=='Strict'
                assert 'campfire-device' not in host.evaluate('document.cookie')
                room_id=host.evaluate("JSON.parse(localStorage.getItem('campfire-room-pointer-v1')).id")
                def snapshot():return store.snapshot(room_id,cookie['value'])
                assert snapshot()['expiresAt']-snapshot()['createdAt']==WEEK
                ok('Leading-zero custom ID, fixed seven-day deadline and HttpOnly identity')
                guest.goto(origin+'/#rooms/004321');entry(guest,'004321','小红',pin='9999')
                expect(guest.locator('#room-entry-message')).to_contain_text('房号或口令')
                guest.locator('#room-passcode').fill('246810');guest.locator('#room-entry-form button[type=submit]').click()
                expect(guest.locator('.room-number')).to_have_text('004321');synced(guest)
                wait_for(lambda:len(snapshot()['members'])==2,host)
                ok('Independent browser joins same room; wrong PIN reveals no room data')
                key='v4-skewers-01'
                vote(host,key).click();synced(host);vote(guest,key).click();synced(guest)
                wait_for(lambda:sum(key in m['choices']['votes'] for m in snapshot()['members'])==2,host)
                vote(host,key).click();synced(host)
                assert snapshot()['selected']==[key]
                ok('Two votes form one menu entry; cancelling one leaves the other intact')
                for p in (host,guest):
                    pane(p,'supplies');p.locator('#room-supply-search').fill('盐')
                    p.locator('[data-room-kind=ingredient][data-id=salt]').check();synced(p)
                host.locator('[data-room-kind=ingredient][data-id=salt]').uncheck();synced(host)
                assert 'salt' in snapshot()['inventory']['ingredients']
                action(guest,'supply-kind','tools').click();guest.locator('#room-supply-search').fill('竹炭')
                expect(guest.locator('[data-id=bamboo-charcoal][data-room-kind=tool]')).to_be_visible()
                guest.locator('[data-id=bamboo-charcoal][data-room-kind=tool]').check();synced(guest)
                guest.locator('#room-supply-search').fill('苹果木');guest.locator('[data-id=apple-wood][data-room-kind=tool]').check();synced(guest)
                assert {'bamboo-charcoal','apple-wood'}<=set(snapshot()['inventory']['tools'])
                ok('Personal supply ownership merges correctly, including bamboo charcoal and apple wood')
                pane(host,'menu');host.locator('#room-people').fill('4');host.locator('#room-people').press('Tab');synced(host)
                host.locator(f'[data-room-portion="{key}"]').select_option('0.5');synced(host)
                pane(guest,'menu');expect(guest.locator('#room-people')).to_be_disabled()
                expect(guest.locator('#room-people')).to_have_value('4',timeout=12000)
                assert snapshot()['settings']['portions'][key]==.5
                assert '350 g' in host.locator('.room-shopping').inner_text()
                ok('Host controls people and portions; net quantities do not multiply with votes')
                member=snapshot()['memberId'];host.reload();expect(host.locator('.room-number')).to_have_text('004321');synced(host)
                assert snapshot()['memberId']==member
                ok('Native reload restores member using HttpOnly cookie, without nickname impersonation')
                # Commit succeeds but HTTP acknowledgement is lost exactly once.
                before=snapshot()['revision'];dropped=[]
                def lose_ack(route):
                    if not dropped:
                        response=route.fetch();assert response.status==200;dropped.append(True);route.abort('failed')
                    else:route.continue_()
                host.route('**/api/rooms/*/ops',lose_ack)
                vote(host,'v4-skewers-02').click()
                synced(host);host.unroute('**/api/rooms/*/ops',lose_ack)
                assert dropped and snapshot()['revision']==before+1
                ok('Lost acknowledgement retries same operation ID exactly once')
                # Offline intention survives native page reload and rejoin, then is replayed.
                offline=[True]
                def block_api(route):
                    if offline[0]:route.abort('internetdisconnected')
                    else:route.continue_()
                guest.route('**/api/rooms/**',block_api)
                pane(guest,'dishes');vote(guest,'v4-skewers-03').click()
                expect(guest.locator('.room-sync.attention')).to_be_visible(timeout=20000)
                assert guest.evaluate("Object.keys(localStorage).some(k=>k.startsWith('campfire-room-op-v1:'))")
                guest.reload();expect(guest.locator('#room-entry-message')).to_contain_text('连接中断',timeout=20000)
                offline[0]=False;action(guest,'resume').click();synced(guest)
                wait_for(lambda:'v4-skewers-03' in snapshot()['selected'],guest)
                ok('Offline intention journal survives native reload and reconnect')
                guest.unroute('**/api/rooms/**',block_api)
                # The same owner on another tab must resolve a stale scalar write explicitly.
                other=page(host_context);other.goto(origin+'/#rooms/004321');synced(other);pane(other,'menu')
                pane(host,'menu')
                def stale_reads(route):
                    if route.request.method=='GET':route.abort('internetdisconnected')
                    else:route.continue_()
                other.route('**/api/rooms/**',stale_reads)
                host.locator('#room-people').fill('6');host.locator('#room-people').press('Tab');synced(host)
                other.locator('#room-people').fill('5');other.locator('#room-people').press('Tab')
                expect(other.locator('.room-conflicts')).to_be_visible(timeout=20000)
                other.unroute('**/api/rooms/**',stale_reads)
                action(other,'resolve-server').click();synced(other)
                expect(other.locator('#room-people')).to_have_value('6')
                other.close()
                ok('Stale host change is not silently last-write-wins; explicit conflict resolution')
                pane(host,'dishes');host.locator('#room-dish-search').fill('羊肉串')
                host.locator('[data-room-action=detail]').first.click();expect(host.locator('#room-recipe-dialog')).to_be_visible()
                expect(host.locator('#room-recipe-dialog')).to_contain_text('什么时候算做好')
                host.keyboard.press('Escape');expect(host.locator('#room-recipe-dialog')).not_to_be_visible()
                assert host.evaluate("document.activeElement.hasAttribute('data-room-action')")
                ok('Recipe dialog has complete cooking guidance and returns keyboard focus')
                host.locator('#room-dish-search').fill('');host.screenshot(path=str(OUT/'rooms-workspace-desktop.png'))
                for width in (320,360,390,520,768,1024,1440):
                    guest.set_viewport_size({'width':width,'height':844})
                    for name in ('dishes','supplies','menu'):
                        pane(guest,name)
                        assert guest.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,name)
                    ok(f'{width}px layout: dishes, supplies, menu without horizontal overflow')
                guest.set_viewport_size({'width':390,'height':844});pane(guest,'dishes');guest.screenshot(path=str(OUT/'rooms-workspace-mobile.png'))
                pane(guest,'supplies');guest.locator('#room-supply-search').fill('');guest.screenshot(path=str(OUT/'rooms-supplies-mobile.png'))
                pane(guest,'menu');guest.screenshot(path=str(OUT/'rooms-menu-mobile.png'))
                # Room page is inactive: no polling and personal selection is independent.
                host.locator('.tabs [data-tab=browse]').click()
                assert host.locator('.bottom-dock').is_visible()
                host.locator('[data-action=toggle]').first.click()
                assert host.evaluate("JSON.parse(localStorage.getItem('campfire-kitchen-state-v2')).selected.length")==1
                ok('Personal offline menu remains separate from collaborative selections')
                host.locator('.tabs [data-tab=rooms]').click();synced(host)
                # Advance server time only. Archive worker is deliberately not run yet.
                clock[0]=snapshot()['expiresAt']
                expect(host.locator('#room-entry-message')).to_contain_text('到期',timeout=15000)
                expect(guest.locator('#room-entry-message')).to_contain_text('到期',timeout=15000)
                assert not host.locator('.room-workspace').count()
                entry(guest,'004321','小红');expect(guest.locator('#room-entry-message')).to_contain_text('到期')
                assert store.freeze_expired()==1
                with store.connection() as db:
                    record=db.execute('SELECT payload,status FROM archives WHERE room_id=?',(room_id,)).fetchone()
                    assert record['status']=='pending' and '小明' not in record['payload'] and '小红' not in record['payload'] and '246810' not in record['payload']
                assert not external and not errors,(external,errors)
                ok('Server hard expiry blocks before cleanup; pending archive is redacted and never read by website')
                ok('No JavaScript errors or external HTTP requests')
                browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=10);listener.close()

if __name__=='__main__':
    report={'mode':'real-http','nativeCookies':True,'nativeStorage':True,'browser':'Chromium','checks':checks,
            'htmlSha256':hashlib.sha256((ROOT/'index.html').read_bytes()).hexdigest(),'productionTest':False}
    try:
        run();report['passed']=True
    except Exception:
        report['passed']=False;report['error']=traceback.format_exc();raise
    finally:
        report['javascriptErrors']=errors;report['externalRequests']=external
        (OUT/'rooms-browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
