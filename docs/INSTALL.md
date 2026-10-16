# Lord of the rings online_CN汉化包：Windows 安装使用说明

## 1. 先确认下载的文件

普通玩家需要下载 Release 附件中的**汉化包 ZIP**。GitHub 自动提供的 Source code ZIP 只是源码，没有 payload 差异数据，不能直接安装。

完整解压后应看到：

```text
汉化包/
  README.md
  安装使用说明.md
  01_校验补丁.cmd
  02_检查游戏版本.cmd
  03_安装汉化.cmd
  04_还原英文.cmd
  05_中断恢复.cmd
  06_还原后清理备份.cmd
  manage.py
  full_manager.py
  delta.py
  install-plan.json
  deployment-policy.json
  payload/                 五个压缩差异文件
```

安装时会额外创建 `work/`（完整汉化候选）、`backups/`（英文原件）和 `installed-receipt.json`（安装收据）。这些不是下载时缺失的文件。

汉化包与 LotroZhItemEnglish 是两个独立组件。安装汉化不要求安装插件；安装插件也不会安装或还原汉化。

## 2. 系统、Python 和空间

适用 Windows 英文 LOTRO 客户端。安装工具要求 **Python 3.11+，建议 Python 3.12**。从 [Python 官方下载页](https://www.python.org/downloads/windows/) 安装正式版；安装时保留 Python Launcher 和 Tcl/Tk。仅有 Windows 商店的 python 命令占位符不代表已安装 Python。

在 PowerShell 中执行：

```powershell
py -3 --version
```

输出应为 3.11 或更新版本。如果没有 `py`，脚本会尝试 `python`；可执行 `python --version` 检查。安装包无需下载翻译模型，无需 CUDA、GPU、第三方 Python 库、原生 DAT DLL 或网络翻译服务。

解压后的补丁目录应放在游戏目录之外，例如 `E:\LOTRO-CN`。不要从 ZIP 内直接运行，不要放到游戏根目录或 x64 目录中，尽量避免临时目录、网络盘和同步中的云盘。保留这个目录直到还原完成。

| 占用位置 | 内容与大致空间 |
|---|---|
| 补丁所在盘 | 下载的差异包，以及运行后约 13.1 GiB 汉化候选、约 12.95 GiB 英文备份 |
| 游戏所在盘 | 安装／还原时约 13.1 GiB 临时资源空间；替换后临时文件释放 |
| 补丁与游戏同盘 | 首次安装建议至少 45 GiB 可用空间 |
| 补丁与游戏分盘 | 补丁盘建议至少 30 GiB，游戏盘至少 15 GiB 可用空间 |

空间数字留有余量，实际以清单内字节数和安装器检查为准。备份是游戏资源原件，不是账号或角色数据。

## 3. 找到自己的游戏安装目录

**所有人的盘符和安装路径都可以不同，不需要改脚本里的路径。** 双击操作时会弹出文件夹选择窗口；命令行也可用 `--game-dir` 指定。

正确目录必须直接包含：

```text
client_local_English.dat
client_surface.dat
client_surface_aux_1.datx
client_surface_aux_2.datx
client_general.dat
```

通常还可以看到启动器和 `x64` 子目录。不要选 x64 本身，不要选 Documents 下的 The Lord of the Rings Online，不要选 Plugins。

独立安装版：右键桌面／开始菜单中的游戏快捷方式，打开属性，查看“目标”或“起始位置”；也可使用“打开文件所在的位置”，然后找到上述五个文件。

Steam 版：在库中右键游戏，选择管理、浏览本地文件，再找到上述五个资源文件所在的同一目录。安装器不假定 Steam 在 C 盘，也不假定库名或目录层级。

快捷方式的 .lnk 文件和游戏 EXE 文件都不是要选择的文件夹。若提示资源缺失，重新选择包含五个 DAT/DATX 的主目录。

## 4. 先完成官方更新并退出游戏

先用官方启动器完成英文客户端更新，关闭游戏和启动器；如果后台仍有 lotroclient、lotrolauncher 或 Turbine 相关进程，安装器会停止。

本版资源快照为 2026-10-16 的已核对英文文件组。**日期相同或启动器版本号相同不等于资源文件完全一致**；支持范围以 `install-plan.json` 中五个原件 SHA-256 为准，包括运行时元数据差异。

如果你已装其他 DAT 修改包，请先按原包说明还原；不要将不同汉化、不同日期的候选和备份混用。目录选择成功只说明路径正确，仍需通过版本校验。

## 5. 校验下载文件和版本

将下载 ZIP 的 SHA-256 与同一 Release 的 `SHA256SUMS.txt` 对照。在 PowerShell 中进入下载目录执行：

```powershell
Get-FileHash -LiteralPath '.\Lord-of-the-rings-online_CN-0.1.0-preview.zip' -Algorithm SHA256
```

双击 `01_校验补丁.cmd`，检查五个差异文件与包内清单一致。它不会打开游戏或安装。校验不能代替来源确认，应从你信任的项目发布页下载。

接着双击 `02_检查游戏版本.cmd`，选自己的游戏主目录：

| 输出状态 | 含义／处理 |
|---|---|
| original | 与本版支持的英文原件完全一致，可以继续安装 |
| full_candidate | 已是本版汉化；核对当前包的备份和收据，不必重复安装 |
| unknown | 版本或资源内容不匹配，停止安装，不要绕过检查或改清单哈希 |

五个文件首次安装都应为 original。unknown 时先确认目录、是否完成官方更新、是否有其他修改；若仍不匹配，等待对应版本汉化包或向维护者提供输出中的文件名和 SHA-256。不要提供账号、密码或完整聊天截图。

## 6. 安装汉化

双击 `03_安装汉化.cmd`，选择与第 5 步相同的游戏主目录。安装器依次：

1. 检查退出状态、路径、差异文件、英文版本和可用空间。
2. 在补丁的 work 目录生成完整汉化副本，逐文件核对目标 SHA-256。
3. 将五个英文原件复制到 backups，重新核对原件哈希。
4. 将全部汉化资源暂存到游戏所在盘；暂存校验后逐文件替换。
5. 记录安装收据。发生可处理错误时，按事务记录尝试恢复到操作前状态。

请等到明确显示安装完成再启动游戏，不要在过程中启动启动器、移动文件夹或删除 work/backups。单文件替换是原子的，整组资源仍依赖事务恢复；突然断电时可能需要第 10 节的 recover。

安装位置在 Program Files 或受保护目录时，可能出现访问拒绝。保持游戏退出，右键 PowerShell 选择“以管理员身份运行”，用第 9 节的完整命令执行；安装器不会修改系统权限、关闭安全软件或自动提升权限。

安装完成后照常使用官方启动器，以英文语言设置启动游戏。需要官方修复或更新前，先按第 8 节还原。

## 7. 安装后如何使用

汉化直接作用于游戏资源，不需要输入 /plugins 命令。可查看角色界面、选项、任务、背包和地图。218 张地图增加中英双语标注，便于对照原地名；这不代表地形或点击区域改变。

商城为独立网页，本版保留英文。外观、剧情和术语仍可能存在误译或排版问题。反馈时写明原文／译文、界面位置和资源版本；不要提交隐私内容。

需要物品英文名时，另装独立 LotroZhItemEnglish 插件，参见它自己文件夹内的使用说明。

## 8. 还原英文和官方更新

退出游戏及启动器，双击同一补丁目录的 `04_还原英文.cmd`，选安装时的同一游戏目录。工具使用同一包的已校验英文备份，还原五个资源文件；不会删除插件。

不要拿另一个补丁目录或别人的 backups 还原。保留原包、work、backups 和收据，直到还原成功。游戏已更新或运行后改变资源哈希时，还原可能停止；此时先保留所有文件并联系维护者审查，不要强制覆盖新版本。

官方更新顺序：先还原英文，确认成功，再开官方启动器更新；更新后重新运行版本检查。若出现 unknown，应等对应新版本补丁。游戏更新覆盖汉化后，不能盲目再装旧包。

## 9. 不使用双击脚本的命令行方式

在**解压后的汉化包目录**打开 PowerShell。以下路径仅为示例，替换成自己的实际路径，保留引号；中文、空格和不同盘符均支持：

```powershell
py -3 manage.py verify
py -3 manage.py check --game-dir 'E:\Games\The Lord of the Rings Online'
py -3 manage.py install --game-dir 'E:\Games\The Lord of the Rings Online'
py -3 manage.py restore --game-dir 'E:\Games\The Lord of the Rings Online'
```

`py -3 manage.py install` 不传路径时弹出文件夹选择窗口；没有 Tk 时可手动用 --game-dir。补丁内没有硬编码的玩家游戏路径，也不通过固定 C/D 盘扫描猜测目录。

## 10. 中断、报错与排查

| 现象 | 处理 |
|---|---|
| py/python 找不到或指向商店 | 安装完整 Python 3.11+；重新开终端检查版本 |
| 文件夹选择窗口不可用 | 用第 9 节 --game-dir 命令指定路径 |
| 找不到五个资源 | 选游戏主目录，不是 x64、快捷方式或文档目录 |
| 游戏／启动器未退出 | 退出后重试，不在工具运行时启动游戏 |
| 源文件 unknown | 版本不匹配，保留输出，不修改清单来绕过 |
| difference/candidate checksum mismatch | 下载损坏、文件被改或重建失败，保留旧备份，重新核验发布包 |
| 空间不足 | 按第 2 节释放空间；汉化未还原时不能删 backups/work |
| PermissionError／访问被拒绝 | 检查目录写权限，必要时以管理员终端执行同一命令 |
| Existing candidate damaged / .building | 保留并检查异常文件；不要覆盖已有有效 backups |
| 发现 operation-journal.json | 先 recover，勿继续 install/restore 或手动删事务文件 |

如果有中断事务，退出所有游戏进程，双击 `05_中断恢复.cmd`，或运行：

```powershell
py -3 manage.py recover --game-dir 'E:\Games\The Lord of the Rings Online'
```

recover 恢复到中断操作之前的状态，可能是英文，也可能是汉化；它与“还原英文”不是同一个动作。恢复成功后再决定是否 restore。没有中断事务时，不需要 recover。

安装／还原失败后，优先保留原目录和收据，避免删掉唯一可用的备份。

## 11. 安全清理和卸载

确认还原英文成功、且游戏与启动器仍退出后，可双击 `06_还原后清理备份.cmd`，或执行：

```powershell
py -3 manage.py cleanup --game-dir 'E:\Games\The Lord of the Rings Online'
```

工具检查同一收据为 restored、当前五个原件匹配、没有未完成事务，然后只删除本包已登记且哈希匹配的 backups 和 work 文件。payload 差异包保留，未来资源版本仍匹配时可以重新生成并安装。

如果不打算再安装，完成还原与清理后可以删除整个补丁文件夹。删除补丁文件夹本身不会还原游戏。独立英文名插件需要按插件说明另行卸载。

## 12. 支持范围与来源

不同盘符、空格或中文路径统一由目录选择和 --game-dir 处理；不同游戏版本、渠道文件或运行时改动仍需严格匹配资源哈希。本版不会自动下载／降级英文游戏，不改账号、客户端 EXE 或商城网页，不启用调试端口。

本包为非官方翻译初稿，不是官方中文客户端。源码、译文、游戏资源片段和字体字形的来源说明随发布材料提供；实际公开范围以维护者发布声明为准。
