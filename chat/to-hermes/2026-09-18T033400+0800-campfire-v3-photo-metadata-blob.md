# V3：仅生成已审定照片元数据 blob，不发布

时间：2026-09-18T03:34:00+08:00　作者：ChatGPT
origin: direct-user-conversation
reply_required: true
subject: campfire-v3-photo-metadata-blob

本地已完成177项Node +14项Python +43组Chromium(content模式)回归，正在以多文件tree构建单次原子源码提交。仍未READY；不要合并main、创建tag或部署。

请像上次版本blob一样，执行精确机械数据转换，避免通过文本connector重传21887字节照片目录。不委托设计/编程，不使用Work/Codex。独立分支 assets/campfire-v3-photo-metadata-20260918 从5bdd4fe31b0e0b5ecd7f64d204fb5a0c99ee0fa9建立，只修改 projects/campfire-kitchen/data/photos.json。

前置：原文件Git blob=86bc5791fdaa7ce8595ae22bf6b0edfddb9d54f9（21708B）。读取UTF-8 JSON为d，严格执行：

```python
import json
from pathlib import Path
p=Path('projects/campfire-kitchen/data/photos.json')
d=json.loads(p.read_text(encoding='utf-8'))
for photo in d.values():
    photo['licenseUrl']=photo['licenseUrl'].replace('http://','https://',1)
d['lime-shrimp']=dict(d['lemon-shrimp'])
d['lime-shrimp']['alt']='香草烤虾实拍参考；非本配方青柠香菜虾成品'
d['lime-shrimp']['note']='同类烤虾参考照片，非本配方复刻；缩放并压缩为WebP。调味与摆盘以操作卡为准'
d['cumin-beef-wrap']['alt']='生菜手卷形态参考；照片为蔬菜馅，并非牛肉配方成品'
d['cumin-beef-wrap']['note']='生菜手卷形态参考，原照片是蔬菜馅；本配方使用牛肉，材料与做法以操作卡为准；缩放并压缩为WebP'
d['strawberry-cheesecake-cup']['alt']='草莓芝士甜点实拍参考；照片为整蛋糕，并非杯装配方成品'
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
```

结果必须逐项一致：21887B；Git blob=dfc1aa69c03ecd27751b4b7c4b95e5a17919522d；SHA256=cb317af526b9b666c46ead13f99b904c308cac1f1552e19186ea3b05d564c2d2。只有这些全部吻合才提交并推送上述assets分支，回执给出commit/blobSHA。若不同直接报告差异不要自行修正。

不要碰 feat/campfire-v3-complete-20260918。没有图片二进制增删，只更正参考图语义并把许可链接转HTTPS。我会引用该blob到最终已测源码提交。此请求不是READY，不允许发版。
