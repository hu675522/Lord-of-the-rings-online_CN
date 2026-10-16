# LotroZhItemEnglish 0.1.4 独立插件使用说明

## 用途

查询并复制物品的英文名，方便在游戏内拍卖行搜索。可以把背包物品拖到插件窗口，也可输入中文名查询。离线名称表有同名候选及非物品标题，请核对实际物品再搜索。

本插件独立安装到用户文档目录，不修改游戏 DAT、客户端 EXE 或商城，不购买／使用物品，也不向公共聊天发送内容。界面默认英文，避免依赖汉化字体；输入仍支持中文。英文客户端拖入物品时本来就可能直接得到英文名。

## 文件夹结构

```text
LotroZhItemEnglish-0.1.4/
  README.md
  使用说明.md
  Install.cmd / Verify.cmd / Uninstall.cmd
  manage.py
  plugin-manifest.json
  Plugins/
    LotroZh/
      LotroZhItemEnglish.plugin
      ItemEnglish/
        Main.lua
        Lookup.lua
        Data/...
```

描述文件必须位于作者目录 LotroZh 中。不要放在 Plugins 根目录，不要把包的外层文件夹直接当 Plugins 放进去。

## 方法一：安装工具

1. 完整解压插件 ZIP 到独立、可长期保留的目录。
2. 安装 Python 3.11+（建议 3.12），退出游戏与启动器。
3. 双击 Verify.cmd，然后双击 Install.cmd。
4. 默认通过 Windows 的“文档”已知文件夹定位游戏 Plugins，支持文档重定向；不是按固定用户名或 C 盘路径猜测。
5. 如果实际游戏读取的是另一个文档目录，可手动指定：

```powershell
py -3 manage.py install --plugins-dir 'E:\My Documents\The Lord of the Rings Online\Plugins'
```

这里选择／指定的是**文档中的 Plugins 目录**，不是游戏安装目录。若已有本插件文件，工具停止而不覆盖，请从旧包卸载或核对旧文件后重试。

安装工具会生成 installed-receipt.json。保留此文件及解压目录，卸载时会用到。文件被修改时会停止，避免删除未知内容。

## 方法二：手动复制，无需 Python

退出游戏，把包内 Plugins 下的 **LotroZh** 文件夹复制到你实际 Windows 文档下的 `The Lord of the Rings Online\Plugins`，保留内部结构。如果没有 Plugins，可自行创建。

文档可能位于 OneDrive 或其他盘，使用资源管理器中的“文档”入口查找。复制后应为 `实际文档\The Lord of the Rings Online\Plugins\LotroZh\LotroZhItemEnglish.plugin`。

手动复制不会生成收据；不要用另一次自动安装的收据卸载手动复制的文件。作者目录中若有其他插件，合并目录时保留它们。

## 游戏内加载

进入角色后依次输入，每条回车：

```text
/plugins refresh
/plugins load LotroZhItemEnglish
```

成功后出现英文名查询窗口。常用命令：

| 命令 | 效果 |
|---|---|
| /zhenitem | 显示窗口 |
| /zhenitem hide | 隐藏窗口 |
| /zhenitem reset | 重置窗口位置并显示 |
| /zhenitem debug | 在本机输出最近查询的名称字节、分片及加载状态 |

拖物品到窗口左侧方框，或在输入框填写中文名后点击 Find。英文结果框里 Ctrl+A、Ctrl+C，打开拍卖行搜索框 Ctrl+V。多个结果用 Prev / Next 翻页。

例：“银碎片的堆积”应得到 `Massive Pile of Silver Scraps`。结果为 0/0 时，先核对中文名是否完全一致；若提示分片加载错误，保留 debug 输出，不要把加载失败当作物品不存在。

## 排错

- 可用插件列表为空：确认游戏实际读取的文档目录，以及描述文件路径和完整解压结构。
- 未知命令：确认已在聊天输入框逐条输入，命令使用英文半角斜杠，且客户端的原生命令资源没有被其他包误改。
- 加载成功但没有窗口：输入 /zhenitem reset；必要时退出游戏重新加载。
- 拖入后无结果：手动输入中文名对照；用 /zhenitem debug 查看状态。版本 0.1.4 会区分词库加载失败与无精确匹配。
- 中文同名：用 Prev / Next 核对，不能保证每个中文译名仅对应一个英文物品。

## 单独卸载

自动安装：退出游戏和启动器，从原解压目录运行 Uninstall.cmd，或 `py -3 manage.py uninstall`。工具逐项核对收据，只删除该包安装且哈希匹配的插件文件。

手动安装：退出游戏后，仅移除 `Plugins\LotroZh\LotroZhItemEnglish.plugin` 和 `Plugins\LotroZh\ItemEnglish` 目录；保留 LotroZh 下其他插件。卸载不会还原汉化 DAT。
