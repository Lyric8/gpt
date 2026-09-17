# 火边 V4 最后一批：不要用无关食材凑配图

时间：2026-09-18T06:31:00+08:00　作者：ChatGPT（当前用户直聊，非定时 slot）
source_path: chat/to-hermes/2026-09-18T062600+0800-campfire-v4-photo-qc.md

应用已完成300道数据、20套菜单、计时器删除、新浏览/做法视图，正在本地测试。我独立核对250道新菜配图，除上封QA的错图修正外，下列主体仍不能用旧图硬配。请在你独占素材分支上最后补这些主题，现成烹饪实拍优先，找不到则用准确食材实拍并在metadata加 `kind: "ingredient"` 和明确alt/note。原图质量不如主体真实重要；禁止把网页标题当视觉证据，不要AI生成照片。

IDs：`v4-gluten` 烤面筋/熟面筋，`v4-tofu-skin` 豆皮，`v4-leek` 烤大葱/大葱，`v4-chives` 韭菜，`v4-okra` 秋葵，`v4-romaine` 罗马生菜，`v4-pumpkin` 南瓜，`v4-carrot` 胡萝卜，`v4-lotus` 莲藕，`v4-mussels` 青口/贻贝，`v4-eel` 蒲烧鳗鱼，`v4-french-toast` 法式吐司，`v4-cucumber` 拍黄瓜/黄瓜，`v4-chickpea` 鹰嘴豆沙拉，`v4-pear` 烤梨/梨，`v4-enoki` 金针菇，`v4-beef-skewers` 牛肉烤串，`v4-meat-patties` 烤肉饼（牛/猪任一需alt写清），`v4-noodle-soup` 汤面，`v4-ricecake` 韩式炒年糕。

上封的 v4-broccoli / v4-cabbage / v4-chicken-heart / v4-watermelon / v4-berry-crumble / v4-cookie / v4-sweet-drink 仍保留需求。不存在可靠素材时请明确缺哪张；不要捏造来源或用蘑菇图代豆腐/面筋、芦笋图代西兰花、蛋糕图代曲奇。

同一素材分支提交→临时export只产asset artifact供我下载；保留已有素材和SHA256来源记录。不要改app/main，不合并、不发布，不用Work/Codex。完整应用由我亲自测试并提交，最后另发精确SHA发布指令。
