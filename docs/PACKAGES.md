# 两个组件分别管理

| 组件 | 安装位置 | 安装入口 | 卸载／还原 |
|---|---|---|---|
| Lord of the rings online_CN汉化包 | 玩家选择的游戏主目录，五个 DAT/DATX | 汉化包中的 03_安装汉化.cmd | 同包 04_还原英文.cmd，之后可用 06 清理 |
| LotroZhItemEnglish 0.1.4 | Windows 文档已知文件夹下的游戏 Plugins | 插件独立文件夹中的 Install.cmd，或手动复制 Plugins | 同包 Uninstall.cmd，或按说明手动移除本插件 |

两部分没有捆绑安装行为。汉化还原不卸载插件，插件卸载不还原汉化。需要普通玩家可安装的版本时下载 Release 的各自附件，GitHub Source code ZIP 不是安装包。

- [汉化详细说明](INSTALL.md)
- [独立插件详细说明](ITEM_PLUGIN.md)
