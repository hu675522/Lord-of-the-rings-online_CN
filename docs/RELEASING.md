# GitHub 发布准备

展示名称：**Lord of the rings online_CN汉化包**。建议仓库名 `Lord-of-the-rings-online_CN`，版本 `0.1.0-preview`（当前为本地发布候选，未上传）。仓库名称仅允许 ASCII 字母、数字、点、连字符和下划线，见 [GitHub 官方说明](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)。

## 本地发布目录

`release/Lord of the rings online_CN汉化包/` 中分开放置汉化包、LotroZhItemEnglish-0.1.4、源码和压缩附件；根目录 SHA256SUMS.txt 对应实际附件字节。目录不包含聊天截图、本机安装收据、反馈历史、测试日志或完整 DAT。开发单元测试源码可以保留。

## 上传时分开处理

1. 仓库提交“源码”目录中的内容，不要在包含模型、游戏资源和个人安装状态的原工作区直接 git add .。
2. 项目简介使用展示名称，仓库路径使用符合规则的 ASCII 名称。
3. 创建 0.1.0-preview 的预发布条目，上传汉化包 ZIP、独立插件 ZIP、SHA256SUMS.txt 和必要来源说明。
4. 发布说明明确英文源文件哈希限制、Windows/Python 要求、空间、备份和还原入口、商城未翻译、译文仍待校对。
5. GitHub 自动生成的 Source code ZIP 不是安装包，引导玩家下载附件。

汉化用压缩分块差异，在匹配英文源上生成已核对的五个 DAT，避免上传十余 GiB 的完整候选。GitHub Release 的单个附件需小于 2 GiB，见 [官方说明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。差异 ZIP 约数百 MiB，以本次实际清单为准。不要把它提交为普通 Git 大文件。

## 对外公开前的来源事项

项目自身代码尚未选定许可证；第三方来源、原生接口参考、游戏文本／图像片段和生成的字体字形见 THIRD_PARTY_NOTICES.md。差异格式减少文件体积，并不会改变资源的来源或许可条件。尤其是本地生成中文字体用到了 Windows 字体，公开分发范围需要维护者确认，或改为授权明确的字体后重新生成并验证。

当前准备工作不代替许可选择，也不会自动创建仓库、推送代码或发布 Release。

## 后续版本维护

保留新的原文版本和源／目标哈希清单。官方更新后重新做资源核验和汉化构建，不以放宽原件哈希方式兼容。全量素材、模型和本机原件为维护者本地资料，不在源码目录内；完整重建尚需对应资料。发行包可使用 Python 标准库独立安装。
