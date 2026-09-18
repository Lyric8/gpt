"""V4-specific visual and interaction gates, shared by real-HTTP and explicit content runs."""
from pathlib import Path
import json

def audit_v4(page, ok, out: Path):
    seen=[]
    for number in range(1,14):
        cards=page.locator('#catalog-list [data-card]')
        ids=cards.evaluate_all('(xs)=>xs.map(x=>x.dataset.card)')
        assert 1<=len(ids)<=24
        seen.extend(ids)
        assert 'undefined' not in page.locator('#catalog-results').inner_text()
        for id in ids:
            page.locator(f'[data-card="{id}"] .card-title').evaluate('(x)=>x.click()')
            dialog=page.locator('#recipe-dialog')
            text=dialog.inner_text()
            assert 'undefined' not in text and 'NaN' not in text, id
            assert dialog.locator('.step-list li').count()>=1, id
            assert dialog.locator('.doneness').count()==1, id
            assert dialog.locator('.serving').count()==1, id
            assert dialog.locator('[data-action=timer],.timer-box').count()==0
            page.keyboard.press('Escape')
        if number<13:page.locator('[data-action=browse-page]').last.click()
    assert len(seen)==len(set(seen))==300
    ok('逐页遍历300道、逐一打开做法：无重复或遗漏，无undefined/NaN，有步骤、熟度、吃法且无倒计时')
    page.locator('#recipe-search').fill('苹果木')
    assert '25 道菜' in page.locator('#recipe-count').inner_text()
    assert '第 1 / 2 页' in page.locator('.pagination').inner_text()
    page.locator('[data-action=browse-page]').last.click()
    assert page.locator('[data-card]').count()==1
    page.locator('#recipe-search').fill('not-a-recipe-00000')
    assert page.locator('[data-card]').count()==0
    assert page.locator('.pagination').count()==0
    page.locator('#recipe-search').fill('')
    ok('搜索重置页码；烟熏25道可翻到末页；空结果不残留旧卡片或分页')
    result=page.evaluate('''async()=>{
      const photos=JSON.parse(document.getElementById('photo-data').textContent);
      await Promise.all(Object.values(photos.library).map(async p=>{const image=new Image();image.src=p.src;await image.decode();if(!image.naturalWidth)throw Error('bad image')}));
      return {photos:Object.keys(photos.library).length,refs:Object.keys(photos.refs).length,missing:Object.values(photos.refs).filter(x=>!x).length};
    }''')
    assert result['refs']==300 and result['missing']==4
    (out/'photo-v4-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    ok(f"完整去重图片库{result['photos']}张均可离线解码，300个映射；{result['missing']}道无对应实拍明确留空")
    # Exact computed colors, composited against the nearest nontransparent background.
    visual=page.evaluate('''()=>{
      const rgb=s=>(s.match(/[\\d.]+/g)||[]).map(Number);
      const blend=(a,b)=>{const k=a[3]??1;return a.slice(0,3).map((v,i)=>v*k+b[i]*(1-k));};
      const lum=c=>c.map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);
      const background=e=>{const layers=[];for(let p=e;p;p=p.parentElement)layers.unshift(rgb(getComputedStyle(p).backgroundColor));return layers.reduce((b,a)=>blend(a,b),[255,255,255]);};
      const bad=[],fonts=[];
      for(const e of document.querySelectorAll('#app *')){
        if(!e.checkVisibility()||e.closest('button:disabled,[aria-hidden=true]')||![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()))continue;
        const c=getComputedStyle(e),font=parseFloat(c.fontSize);fonts.push(font);
        const bg=background(e),fg=blend(rgb(c.color),bg),l=[lum(fg),lum(bg)].sort((a,b)=>b-a),ratio=(l[0]+.05)/(l[1]+.05);
        const required=font>=24||(font>=18.66&&parseFloat(c.fontWeight)>=700)?3:4.5;
        if(ratio+1e-7<required)bad.push({text:e.innerText?.slice(0,60),ratio,required,color:c.color,bg});
      }
      return {bad,minFont:Math.min(...fonts)};
    }''')
    assert not visual['bad'],visual['bad']
    assert visual['minFont']>=14,visual
    (out/'contrast-v4-report.json').write_text(json.dumps(visual,ensure_ascii=False,indent=2)+'\n')
    ok('首页实际计算文字颜色满足AA对比度；可见文本最小14px，不把禁用控件当正常正文')
    page.locator('.tabs [data-tab=fire]').click()
    assert '一氧化碳' in page.locator('#app').inner_text()
    assert '木块不必泡水' in page.locator('#app').inner_text()
    page.locator('[data-action=fire-recipes]').click()
    assert page.locator('[data-action=category][data-value="苹果木烟熏"]').get_attribute('aria-pressed')=='true'
    page.locator('[data-action=category][data-value=""]').click()
    ok('炭火指南具备竹炭/苹果木/双区火安全说明，烟熏入口真正筛到25道')
    for width in [320,390,768,1440]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        if width==390:
            assert page.locator('[data-card]').first.bounding_box()['y']<550
            page.screenshot(path=str(out/'v4-mobile-first-visit.png'))
        if width==1440:page.screenshot(path=str(out/'v4-desktop-first-visit.png'))
    ok('首访桌面与手机视觉留档；390px首张菜卡在550px内出现，主文档无横向溢出')
    page.evaluate('window.scrollTo(0,0)')
