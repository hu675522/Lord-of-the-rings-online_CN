# 开发与本地验证

## 最小测试环境

本机已使用 Windows、Python 3.12 和 Pillow 12.3.0 验证。普通代码测试不需要完整游戏、GPU、模型或原生 DAT DLL。

从项目根目录运行：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试在临时假游戏目录中操作，不部署到真实游戏。字体测试需要 `C:\Windows\Fonts\msyh.ttc`；缺少该字体会跳过相应测试。系统字体不随源码分发，跳过测试不等于字体实测通过。

若系统临时目录受限：

```powershell
New-Item -ItemType Directory -Force .test-tmp | Out-Null
$env:TEMP = (Resolve-Path .test-tmp).Path
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 验证的区别

| 命令 | 所需资料 | 验证内容 |
|---|---|---|
| `python -m unittest discover -s tests -v` | 源码、Pillow | 编解码、参数保护和夹具回滚等行为 |
| `python tools/verify_artifact_files.py --manifest localization/full/manifest.json` | 已生成的完整素材 | 文件与清单中的 SHA-256 一致 |
| `python localization/full_verify.py`、`python localization/full_font_verify.py` | 素材及匹配原始备份 | 资源结构、原始字形／像素和译文素材对应 |

这些检查不代替译文语义或真实游戏验证。

## 本地数据与完整重建

原始备份、候选、安装计划、`catalog.sqlite3`、`full/`、历史批次、模型、CUDA 依赖、运行时配置及收据不在源码包内。缺少这些资料时，不要直接运行所有构建脚本；源码克隆尚不是自动重建全量补丁的完整环境。

已有匹配备份和翻译记忆的完整工作区可执行：

```text
python localization/apply_full_corrections.py
python localization/full_context_corrections.py
python localization/fix_creation_feedback.py
python localization/fix_chat_selection_feedback.py
python localization/full_translate.py refresh
python localization/full_preflight.py
python localization/full_build.py
python localization/full_verify.py
python localization/build_fonts.py localization/full
python localization/full_font_verify.py
python localization/full_report.py
```

这些步骤更新工作区，不安装到游戏。先备份自行修订的翻译记忆。`full_corrections.json` 的单元编号绑定当前任务数据库，不能直接用于其他基线或重新编号的数据库。

初始提取、模型下载、转换和全量重建的便携化仍待完成。本地推理使用 CTranslate2、SentencePiece 和 CUDA；普通玩家核对文件或未来安装预构建包不应被要求运行翻译模型。

## 旧入口与原生写入器

`native/DatPatchWorker.cs` 通过 `DatExport.dll` 修改工作区副本，写入限制在相邻的 `client_patch/work`。二进制库和 EXE 不随源码预览分发。

`build_client_patch.py` 仍是两个任务的旧验证构建入口，依赖本机 `runtime.json`、原文快照和原生库，不会自动将全量 SQLite 封装为 DAT。全量流程使用独立入口：

```text
python build_full_patch.py
```

它校验完整备份和素材，在 `client_patch/full/work/` 创建副本，用 `native/FullDatPatchWorker.cs` 流式写入并独立读回验证。需要本机完整素材、原始备份、32 位访问库及 .NET Framework C# 编译器，不调用翻译模型。已有候选计划时停止，避免覆盖。

`client_patch/full_manager.py` 构建时复制为包内 `manage.py`，不绑定开发机 Python 路径。真实写入要求明确游戏目录、匹配哈希、可用备份及已关闭的客户端；默认策略禁止安装，恢复功能仍可用。

`tools/test_full_installation.py` 仅供已有完整候选的本机验证，在 `.test-tmp/` 内用完整大小的四文件夹具测试安装与还原，需要额外复制和暂存空间。只有测试夹具策略会启用，真实包和游戏不会因此开放部署。

译文修订方式见 [参与校对](../CONTRIBUTING.md)。
