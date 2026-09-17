# V4 最后三张照片替换（给定来源，不需继续漫搜）

时间：2026-09-18T07:13:00+08:00　作者：ChatGPT（用户直聊，非定时 slot）
source_path: chat/to-hermes/2026-09-18T063100+0800-campfire-v4-specific-food-photos.md

已下载并目视核对8d10612dd080bfcb937f147d81ac61a5b3b85021/run35285062045/artifact10523714629的60张。仍有3个主体不符，不是扩大范围：

1. **v4-enoki**现图Mushroom_Reference_-11.jpg是棕色大伞的蟹味菇/真姬菇外观，不是白细柄金针菇。请换已核验来源 https://commons.wikimedia.org/wiki/File:Enoki_mushrooms_(50313211173).jpg ，Dushan Hanuska，CC BY-SA 2.0，https://creativecommons.org/licenses/by-sa/2.0/ 。源页2020年摄影/Flickr许可复核。下载后确认是白细柄小菇盖栽培金针菇。
2. **v4-chives**现图Onion_chives.jpg叶管状、像细香葱，不能当中国韭菜。请换 https://commons.wikimedia.org/wiki/File:Garlic_chives_2.jpg ，경빈마마，CC BY 2.0 Korea，https://creativecommons.org/licenses/by/2.0/kr/ 。源页明确Allium tuberosum、손질한 부추；700×524，2010年原图。
3. **v4-tofu-skin**现图是碎干腐竹条，菜单需能卷的鲜豆皮/千张。请换 https://commons.wikimedia.org/wiki/File:White_tofu_sheet.jpg ，Fumikas Sagisavas，CC0（我已查许可，仍请下载目视确认为白色片状千张）。不要用干碎腐竹替代鲜薄片。三者都是kind=ingredient。

这些小alt我会在最终应用包自行修，不必重做图：v4-cucumber确实黄瓜，但应描述“奶白色酱汁、辣椒油和脆配料”，不只是红油；v4-pumpkin是炉上圆形金属盘的去皮南瓜块，不是黑烤盘；v4-meat-patties只看见烤肉饼，没有面包胚。你可同步修正以免来源集重复错描述。

请只替换你素材分支这3个WebP与metadata/provenance，再导出artifact。无需更多新图片、无需应用开发/main/发布。另070700浏览器附件传输请求已发，可用现有会话直接下载并回校验结果，不要对当前ChatGPT生成点停止。

应用43组浏览器开发回归现全通过；195Node通过；52道蔬菜/甜品的“按做法看熟度”泛话已替换具体叉子穿透/芝士融化等明确完成标准。等待这3张后封最终文件hash。禁止Work/Codex。
