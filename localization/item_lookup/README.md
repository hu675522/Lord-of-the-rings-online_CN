# LotroZhItemEnglish 0.1.4

独立游戏内物品英文名查询插件。完整安装、加载、拖入／输入查询、复制和卸载步骤见 [使用说明](../../docs/ITEM_PLUGIN.md)。

名称表含 147,738 个规范化中文入口，4,548 个有多个英文候选；包含非物品标题，计数不是可交易物品数。

开发构建：

```powershell
py -3 localization/item_lookup/build_lookup.py
py -3 tools/verify_item_lookup_lua.py
py -3 localization/item_lookup/package_lookup.py
```

需要本地翻译资源库；普通玩家使用生成的独立附件，不运行构建脚本。分片采用 ASCII Lua 源码及 UTF-8 字节转义，持久全局注册，并区分加载失败和无匹配。
