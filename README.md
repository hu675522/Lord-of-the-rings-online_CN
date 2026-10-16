# Lord of the rings online_CN汉化包

《The Lord of the Rings Online》非官方简体中文汉化，适用于 Windows 英文客户端。

包含游戏文本、中文字体、218 张中英双语地图。

译文以机器初稿为主，术语和长文本仍可继续校对；商城网页暂不汉化。

## 下载与目录

[下载 0.1.0-preview 汉化包和独立插件](https://github.com/hu675522/Lord-of-the-rings-online_CN/releases/tag/v0.1.0-preview) · [反馈问题](https://github.com/hu675522/Lord-of-the-rings-online_CN/issues)

汉化包和插件分别下载；附件 SHA-256 见同一发布条目的 SHA256SUMS.txt。

| 内容 | 用途 |
|---|---|
| 汉化包 ZIP | 玩家安装：解压后选择自己的游戏目录；自动校验、生成汉化文件、备份和安装 |
| LotroZhItemEnglish-0.1.4 ZIP | 可选独立插件，查询和复制物品英文名，便于拍卖行搜索 |
| GitHub 的 Source code ZIP | 开发源码，不能直接当汉化包安装 |

[汉化安装、备份、还原与排错](docs/INSTALL.md) · [独立插件说明](docs/ITEM_PLUGIN.md) · [两个组件如何分别管理](docs/PACKAGES.md)

## 安装概览

1. 下载真正的“Lord-of-the-rings-online_CN-0.1.0-preview.zip”，完整解压到游戏目录以外的固定文件夹。
2. 安装 Python 3.11 或更新版本，建议 Python 3.12，保留安装器中的 Tcl/Tk 和 Python Launcher。
3. 退出游戏与启动器，依次运行 `01_校验补丁.cmd`、`02_检查游戏版本.cmd`、`03_安装汉化.cmd`
4. 在目录选择窗口中选中本机 LOTRO 主目录。

   该目录应直接包含 `client_local_English.dat` 等五个资源文件，不能选择 `x64`、文档 Plugins 或启动器快捷方式。
6. 保留补丁目录下的 backups、work 和安装收据，之后通过 `04_还原英文.cmd` 还原。

首次安装同一磁盘建议预留 45 GiB 可用空间。补丁只支持发布清单中指定的英文文件版本；路径可以不同，但资源版本必须匹配。详见完整说明。

## 覆盖范围

- 本版实际修改 746,067 个文本片段、271,495 个文本资源。
- 包含中文字体、界面、任务和物品名称初稿，以及 218 张双语地图。
- 保留一条已知服务器更新的等级礼包原文。
- 不修改客户端 EXE，不开启网页调试端口，不安装 Windows 中文助手。
- 汉化与英文名插件分别安装和卸载。

发布使用 SHA-256 绑定的分块差异包，在玩家电脑上从匹配的英文资源生成汉化文件，不分发十余 GiB 的完整 DAT。新安装器的路径处理和差异重建单独验证，不把此前的汉化内容体验等同于所有电脑兼容。

## 开发与发布

[开发说明](docs/DEVELOPMENT.md) · [发布准备](docs/RELEASING.md) · [来源与许可](THIRD_PARTY_NOTICES.md) · [变更记录](CHANGELOG.md)

仓库地址：https://github.com/hu675522/Lord-of-the-rings-online_CN

当前发布为预发布版，不代表全量人工校对已完成。
