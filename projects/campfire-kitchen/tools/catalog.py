#!/usr/bin/env python3
"""Compile the reviewed, explicitly enumerated V4 catalog; never generate flavor products.

Source contract: manifest + preserved classics + ingredient definitions + pipe-separated
recipe records. Each record is an authored dish with its own preparation, cooking and
serving instructions. Runtime remains schemaVersion=2 for backup compatibility.
"""
from __future__ import annotations
import argparse
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = {
    'skewer': ('炭火串烤', ['炭烤炉与烤网','烧烤炭','金属烤签','生熟两夹','隔热手套']),
    'grill': ('直接炭烤', ['炭烤炉与烤网','烧烤炭','生熟两夹','隔热手套']),
    'basket': ('烤篮炭烤', ['炭烤炉与烤网','烧烤炭','烧烤篮','生熟两夹','隔热手套']),
    'fish': ('夹网炭烤', ['炭烤炉与烤网','烧烤炭','烤鱼夹','生熟两夹','隔热手套']),
    'roast': ('加盖间接烤', ['带盖双区炭烤炉','烧烤炭','炉温计','生熟两夹','隔热手套']),
    'smoke': ('苹果木热烟熏', ['带盖双区炭烤炉','烧烤炭','苹果木烟熏木','炉温计','探针温度计','生熟两夹','隔热手套','耐热浅盘']),
    'pan': ('煎盘料理', ['带沿煎盘（无漏油孔）','夹子/铲子']),
    'pot': ('一锅煮焖', ['至少3L带盖锅','勺子']),
    'cold': ('冷拌 / 组装', ['搅拌碗','勺子']),
}
FIRE = {
    'skewer': '竹炭负责供热。炭烧透后分成有炭区与无炭区，先在中火处烤串；滴油起火就移到无炭侧。',
    'grill': '竹炭烧透后留出无炭区。直火上色，弱火完成；不把食物放在持续火苗上烧。',
    'basket': '竹炭烧透后用中火区。小食材放烤篮，留出通风间隙；菜篮不要压灭炭火。',
    'fish': '竹炭烧透，烤鱼夹和鱼皮薄刷油。烤网一侧留空，鱼皮上色后可移到弱火处。',
    'roast': '竹炭供热，食物放在无炭侧，合盖后靠热空气烤熟。按步骤控制炉温，进排气口不能全关。',
    'smoke': '竹炭供热，苹果木增香。带盖炉设双区火，食物放无炭侧；初次从一小块干燥食品烟熏苹果木开始，按炉具和木块规格减量。木块不必泡水；先散掉呛鼻浓烟，保持薄烟与通风，不持续填木。',
    'pan': '煎盘只占炉面一部分，进排气保持畅通。先用中火，糖酱与奶制品改小火；也可用适配的卡式炉。',
    'pot': '锅要放稳，不封住炉体进气。煮开后转小火，奶、淀粉与浓酱需要搅动防糊；也可用适配的卡式炉。',
    'cold': '不用生火。熟食用单独刀板，奶制品、熟肉和切好的果蔬随取随冷藏。',
}
POULTRY = {'chicken','chickenWing','chickenDrum','chickenWhole','chickenBreast','chickenHeart','chickenGizzard','chickenSkin','chickenGround','duckBreast','quail'}
GROUND = {'groundBeef','lambGround','sausageRaw'}
WHOLE = {'beefSteak','lambChop','porkChop','porkTender','porkRibs','porkShoulder'}
CUT_MEAT = {'porkBelly','porkNeck','beefFlank','beefTongue','lamb','beef','bacon'}
FISH = {'salmon','fish','wholeFish','trout','mackerel','cod','sardine'}
SEAFOOD = {'shrimp','prawnShell','scallopMeat','squid'}
REHEAT = {'rice','noodleCooked','sausageCooked','ham','octopusCooked','eelCooked','crabCooked'}
CATEGORIES = ['串烤','炭烤大肉','海鲜烧烤','苹果木烟熏','烤蔬菜','豆类与菌菇','主食','一锅与煎盘','冷菜与蘸酱','甜品','饮品']


def read_rows(path: Path, lengths: set[int]) -> list[list[str]]:
    out=[]
    for line, text in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not text.strip() or text.startswith('#'):
            continue
        cells=[x.strip() for x in text.split('|')]
        if len(cells) not in lengths or any(not cell for cell in cells[:-1]):
            raise ValueError(f'{path.name}:{line}: invalid record ({len(cells)} fields)')
        out.append(cells)
    return out


def safe_path(root: Path, name: str) -> Path:
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f'Catalog source outside project or missing: {name}')
    return path


def completion(ids: set[str], mode: str, title: str) -> str:
    notes=[]
    if ids & POULTRY:
        notes.append('禽肉最厚处中心至少74℃，探针避骨；鸡肉末、内脏与卷入夹层也要测到。')
    elif ids & GROUND:
        notes.append('肉末或生香肠中心至少71℃；肉丸浮起、外皮变色都不能替代测温。')
    elif ids & CUT_MEAT or ('卷' in title and ids & WHOLE):
        notes.append('薄切、折叠或卷起的肉按中心至少74℃完成，展开或切开最厚处核对，不留夹生层。')
    elif ids & WHOLE:
        notes.append('整切猪牛羊肉中心至少63℃，离火静置至少3分钟；肋排、猪肩达到安全温度后仍需继续烤到软嫩。')
    if ids & FISH:
        notes.append('鱼肉最厚处中心至少63℃；检查细刺。')
    if ids & SEAFOOD:
        notes.append('虾、扇贝与鱿鱼必须全部熟透；虾和扇贝肉应呈珍珠白或白色且不透明，厚块检查中心。')
    if 'oysterMeat' in ids:
        notes.append('去壳蚝肉先在沸水中煮至少3分钟，再进行烤制；全程使用分开的生熟容器。')
    if ids & {'clams','mussels'}:
        notes.append('活贝按步骤开壳后继续煮3—5分钟，未开壳的弃掉；不吃破壳、死贝。')
    if mode != 'cold' and ids & REHEAT:
        notes.append('冷藏熟食复热至中心至少74℃，尤其是熟米饭与面条。')
    if ids & {'egg','eggWhole'}:
        notes.append('蛋白与蛋黄均凝固；混合蛋料理中心至少71℃，含禽肉时按74℃。')
    if not notes:
        notes.append('按步骤检查中心软熟与口感；表面焦黑的部分不吃，不能只看颜色或分钟数。' if mode!='cold' else '即食原料与容器保持清洁；冷菜临吃再拌，易腐食品保持≤4℃冷藏。')
    return ''.join(notes)


def load_catalog(root: Path = ROOT) -> dict:
    manifest=json.loads((root/'data/recipes.json').read_text(encoding='utf-8'))
    if 'catalogSource' not in manifest:
        return manifest
    if manifest.get('schemaVersion')!=2 or manifest['catalogSource']!=1:
        raise ValueError('Unsupported catalog source version')
    db=json.loads(safe_path(root,manifest['base']).read_text(encoding='utf-8'))
    db.update(version=manifest['version'],title='火边 · 300道露营菜谱',updated='2026-09-18')
    for id,name,unit,group,allergens in read_rows(safe_path(root,manifest['ingredients']),{5}):
        if id in db['ingredients'] or not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]*',id):
            raise ValueError(f'Duplicate or invalid ingredient: {id}')
        chilled=group in {'生鲜肉类','海鲜','冷藏熟食','豆制品','乳制品','蔬菜','水果','香草'}
        db['ingredients'][id]={'name':name,'unit':unit,'group':group,'storage':'≤4℃冷藏，遵循包装期限；生熟分开。' if chilled else '密封防潮；开封后按包装要求保存。','note':'重量按名称标注形态计算；复合调味料、加工肉与包装食品的过敏原以实物标签为准。','allergens':allergens.split(',') if allergens else [],'pantryHint':False}
    db['sources'].update({
        'v4-temperature':{'title':'FoodSafety.gov · 食品中心安全温度','url':'https://www.foodsafety.gov/food-safety-charts/safe-minimum-internal-temperatures','scope':'安全温度依据；配方与用量为火边自行设计，不代表来源机构实测或背书。'},
        'v4-fire':{'title':'Weber · 双区炭火与加盖烟熏','url':'https://www.weber.com/US/en/blog/tips-techniques/how-to-smoke-on-a-charcoal-grill/weber-29697.html','scope':'双区火、加盖、木块不必泡水与通风原则；具体炉温与用量需按实际设备调整。'},
        'v4-cold':{'title':'FoodSafety.gov · 清洁、分开、煮熟、冷藏','url':'https://www.foodsafety.gov/keep-food-safe/4-steps-to-food-safety','scope':'冷藏与室温时间边界，生熟分离；不冲洗生禽肉以免飞溅污染。'},
        'v4-co':{'title':'CDC · 木炭与一氧化碳','url':'https://www.cdc.gov/carbon-monoxide/about/index.html','scope':'炭火不进帐篷、车内、室内及封闭空间；看起来无烟或灰白的炭仍会产生一氧化碳。'},
        'v4-shellfish':{'title':'CDC · 安全处理与烹调贝类','url':'https://www.cdc.gov/vibrio/prevention/index.html','scope':'贝类需彻底熟制，柠檬、辣酱与酒不能杀灭生蚝中的有害病原体。'},
    })
    # Keep all original IDs and quantities so V2/V3 menu notes and backups remain meaningful.
    for old in db['recipes']:
        old['category']={'肉类':'一锅与煎盘','海鲜与汤':'一锅与煎盘','蔬菜':'烤蔬菜','开胃与冷菜':'冷菜与蘸酱','甜品与饮料':'饮品' if old['id'] in {'virgin-mojito','basil-berry-soda','spiced-hot-apple'} else '甜品'}.get(old['category'],old['category'])
        old['photoId']=old['id']
        old['fireSetup']=old['smoke']
        old['completion']=completion({r['ingredient'] for r in old['ingredients']},'pan',old['title'])
        old['serving']=old['fun']
    for fragment in manifest['fragments']:
        rows=read_rows(safe_path(root,fragment['path']),{8,9})
        if len(rows)!=fragment['count']:
            raise ValueError(f'{fragment["path"]}: expected {fragment["count"]}, got {len(rows)}')
        for number,row in enumerate(rows,1):
            title,parts,prep,cook,serve,photo,times,mode,*extra=row
            if mode not in MODES:
                raise ValueError(f'{title}: invalid cooking mode {mode}')
            active,total=map(int,times.split('/'))
            ingredients=[]
            for part in parts.split(','):
                id,qty=part.split(':')
                if id not in db['ingredients']:
                    raise ValueError(f'{title}: missing ingredient {id}')
                ingredients.append({'key':id,'ingredient':id,'qty':float(qty),'form':'按准备步骤处理','stage':'在家','scaling':'linear','pack':'按原料储存要求分装；生鲜与即食食材分开。'})
            ids={r['ingredient'] for r in ingredients}
            if len(ids)!=len(ingredients):
                raise ValueError(f'{title}: duplicate ingredient')
            technique,tools=MODES[mode]
            tools=list(tools)+['刀与砧板']
            if mode in {'pan','pot'}:
                tools.append('安全热源')
            if mode in {'grill','basket','fish','skewer','roast'} and ids & (POULTRY|GROUND|WHOLE|CUT_MEAT|FISH|SEAFOOD|REHEAT):
                tools.append('探针温度计')
            if extra and extra[0]:
                tools+=extra[0].split(',')
            category=fragment['category']
            if fragment['id']=='sweets' and number>=14:
                category='饮品'
            step_parts=[part.strip()+'。' for part in cook.rstrip('。').split('；') if part.strip()]
            item={
                'id':f'v4-{fragment["id"]}-{number:02d}','title':title,'category':category,
                'basePeople':2,'ingredients':ingredients,'steps':step_parts,'prep':[prep],
                'tip':completion(ids,mode,title),'completion':completion(ids,mode,title),'smoke':FIRE[mode],'fireSetup':FIRE[mode],
                'fun':serve,'serving':serve,'equipment':list(dict.fromkeys(tools)),
                'activeMinutes':active,'totalMinutes':total,'homeMinutes':15,'rank':100+number,
                'main':ingredients[0]['ingredient'],'sources':['v4-temperature','v4-cold']+(['v4-fire','v4-co'] if mode in {'grill','basket','fish','skewer','roast','smoke'} else [])+(['v4-shellfish'] if ids & {'clams','mussels','oysterMeat'} else []),
                'tags':[category,technique]+(['竹炭','烧烤'] if mode in {'grill','basket','fish','skewer','roast','smoke'} else [])+(['苹果木','果木','烟熏'] if mode=='smoke' else []),
                'technique':technique,'difficulty':'需要控温' if mode in {'smoke','roast'} else '按步骤操作',
                'origin':'火边自行设计的两人分享配方；参考公开食品安全和烹饪原则，未逐道在你的炉具上实做验证。',
                'cleanup':'完全冷却后按炉具说明清理炭灰与油盘；奶油、糖酱锅具及时清洗。' if mode!='cold' else '熟食刀板与生肉刀板分开清洗。',
                'batchNote':'食物单层排开，放不下就分批；加倍份量不等于原炉面能同时烤完。',
                'revision':1,'batchFactor':1,'policy':'按食材种类筛选；仍需核对合计数量。',
                'hold':'易腐食品保持≤4℃；室温累计不超过2小时，环境高于32℃不超过1小时，超过则弃食。',
                'profile':category,'taste':serve.split('，')[0].rstrip('。'),'texture':technique,'textureFamily':category,
                'moment':'趁热上桌' if mode!='cold' else '临吃现拌','why':'切法、上火顺序与吃法按本菜步骤执行。',
                'decisions':[f'采用{technique}，切法与加热顺序见准备和步骤；增加份量时按炉面容量分批。'],'needsFreezer':False,'freshHerbs':[id for id in sorted(ids) if db['ingredients'][id].get('freshHerb')],
                'interaction':'动手' if active>=25 else '轻操作','rich':bool(ids&{'porkBelly','bacon','butter','cream','cheddar'}),
                'light':mode=='cold' or category in {'烤蔬菜','豆类与菌菇'},'serveClass':'冷食' if mode=='cold' else '热食',
                'checkMinutes':0,'allergens':sorted({a for id in ids for a in db['ingredients'][id]['allergens']}),
                'photoId':photo if photo!='-' else '',
            }
            db['recipes'].append(item)
    names=[r['title'] for r in db['recipes']]
    if len(names)!=manifest['expectedCount'] or len(set(names))!=len(names):
        raise ValueError('Recipe count or unique title gate failed')
    # Show actual fire cooking first, while retaining every original stable recipe ID.
    order={r['id']:n for n,r in enumerate(db['recipes'])}
    db['recipes'].sort(key=lambda r:(CATEGORIES.index(r['category']) if r['category'] in CATEGORIES else 20,order[r['id']]))
    db['presets'] += [
        {'id':'v4-skewer-table','name':'串烤一桌','note':'羊肉串＋鸡腿葱串＋韭菜＋烤馒头＋拍黄瓜；两人先从每道半份开始。','selected':{'v4-skewers-01':0.5,'v4-skewers-02':0.5,'v4-vegetables-03':0.5,'v4-staples-13':0.5,'v4-cold-01':0.5}},
        {'id':'v4-apple-table','name':'苹果木第一炉','note':'鸡翅、玉米用同一炉160—170℃间接热熏；冷菜最后拌。熟度分别检查，不按同一时间出炉。','selected':{'v4-smoke-01':1,'v4-smoke-16':0.5,'v4-cold-02':0.5}},
        {'id':'v4-seafood-table','name':'海鲜烧烤夜','note':'整鱿鱼＋蒜蓉虾＋杏鲍菇＋蒜香馒头；生熟工具分开。','selected':{'v4-seafood-06':0.5,'v4-seafood-01':0.5,'v4-vegetables-20':0.5,'v4-staples-13':0.5}},
        {'id':'v4-burger-table','name':'汉堡热狗局','note':'汉堡和热狗任选一种为主，配焦糖洋葱与冷沙拉；本套默认汉堡。','selected':{'v4-staples-01':1,'v4-vegetables-12':0.5,'v4-cold-08':0.5}},
    ]
    db['principles']=['先选玩法，再选食材与工具；“齐备”只代表种类齐，不代表数量够。','两人分享量为基准，菜单页可调人数与每道份量。','分钟是安排用餐的估计，不是熟度承诺；以中心温度和本菜完成标准为准。','烟熏只做加热熟制，不做低温冷熏、腌制保存或罐藏。']
    return db


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    text=json.dumps(load_catalog(args.root),ensure_ascii=False,separators=(',',':'))+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text,encoding='utf-8')
    else:
        print(text,end='')
