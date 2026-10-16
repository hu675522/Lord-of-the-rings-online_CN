# 第三方来源与许可记录

本文件记录来源，不替全部组成部分指定同一许可证。项目自身代码的许可证尚待维护者确定，目前不声明整个项目采用 MIT 或 GPL。

| 内容 | 本地用途／来源 | 源码预览的处理 |
|---|---|---|
| LOTRO 英文文本、DAT、图像和资源 | 本机游戏和原始备份 | 不含完整游戏资源、全量原文库及候选 DAT；小型示例和词表的公开范围仍需审阅 |
| Windows `msyh.ttc` | 本机生成汉字字形 | 源码不复制原字体或纹理；发布候选差异中含生成的字体纹理，公开范围待确认或换用可分发字体 |
| Elanor 原生 DAT 库 | 本机依赖，来源记录为 [Endevir/Elanor](https://github.com/Endevir/Elanor) | 不复制 DLL／EXE；保留本机已有 `client_patch/tools/Elanor-GPL-3.0.txt`，实际库版本和适用范围待核对 |
| DAT 布局参考 | [Mirarkitty/lotro_mesh_viewer](https://github.com/Mirarkitty/lotro_mesh_viewer)，代码内保留参考 | 记录来源，不把参考自动视作整个项目的许可结论 |
| Helsinki-NLP/opus-mt-en-zh | [模型页面](https://huggingface.co/Helsinki-NLP/opus-mt-en-zh)，原始包来自 Tatoeba-MT | 不复制模型。原始包 `LICENSE` 标题为 Attribution 4.0 International（CC BY 4.0），需分别核对页面标注及具体分发文件 |
| CTranslate2、SentencePiece、NumPy、PyYAML | 离线推理／模型转换 | 不复制 `vendor/`；实际分发前按版本核对来源与许可 |
| NVIDIA CUDA 库 | 本地 GPU 推理 | 不复制 `cuda-libs/` |
| Pillow | 字体处理和测试 | 通过开发依赖安装，不复制安装目录 |

保留已有许可证文本不等于证明某个二进制可按预想方式再分发。本次未将模型、系统字体、原生二进制或完整游戏资源加入源码预览。实际公开前按 [发布清单](docs/RELEASING.md) 确定范围与许可证。

发布候选差异包不附模型、系统字体原文件、DAT 原件、原生 DLL 或完整候选。它仍含修改后的游戏资源片段及生成的汉字图像；压缩／差异格式不改变这些组成部分的来源条件。
