"""Assemble local release assets without installing, pushing or publishing."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prepare_github_source import prepare
from distribution import delta

BUNDLE = ROOT / 'release/Lord of the rings online_CN汉化包'


def archive_tree(folder, target):
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(folder.rglob('*')):
            if file.is_file():
                if '.git' in file.relative_to(folder).parts:
                    continue
                if file.is_symlink() or not file.resolve().is_relative_to(folder.resolve()):
                    raise ValueError('Unexpected release link')
                if file.name == 'installed-receipt.json' or '__pycache__' in file.parts:
                    raise ValueError('Local runtime state in release')
                archive.write(file, (Path(folder.name) / file.relative_to(folder)).as_posix())
    with zipfile.ZipFile(target) as archive:
        if archive.testzip():
            raise ValueError('ZIP integrity failure')


def main():
    lang = BUNDLE / '汉化包'
    if not (lang / 'install-plan.json').exists():
        raise ValueError('Build language difference bundle first')
    # Always refresh code/docs before archiving; payloads retain pinned hashes.
    for source, target in [('distribution/manage.py','manage.py'), ('distribution/delta.py','delta.py'),
                           ('client_patch/full_manager.py','full_manager.py'), ('docs/INSTALL.md','安装使用说明.md')]:
        shutil.copyfile(ROOT / source, lang / target)
    shutil.copyfile(ROOT / 'THIRD_PARTY_NOTICES.md', lang / '来源与许可.md')
    notice = lang / '来源与许可.md'
    notice.write_text(notice.read_text(encoding='utf-8').replace('[发布清单](docs/RELEASING.md)',
                       '发行方的发布清单'), encoding='utf-8')
    plugin = BUNDLE / 'LotroZhItemEnglish-0.1.4'
    plugin.mkdir(exist_ok=False)
    generated = ROOT / 'localization/item_lookup/generated'
    manifest = json.loads((generated / 'manifest.json').read_text(encoding='utf-8'))
    for row in manifest['records']:
        source = generated / row['file']
        if delta.digest(source) != row['sha256']:
            raise ValueError('Plugin payload changed')
        target = plugin / row['file']; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    shutil.copyfile(generated / 'manifest.json', plugin / 'plugin-manifest.json')
    shutil.copyfile(ROOT / 'localization/item_lookup/standalone_manager.py', plugin / 'manage.py')
    shutil.copyfile(ROOT / 'docs/ITEM_PLUGIN.md', plugin / '使用说明.md')
    (plugin / 'README.md').write_text('# LotroZhItemEnglish 0.1.4\n\n独立的物品英文名查询插件。\n'
        '先阅读 [使用说明](使用说明.md)。可直接手动复制 Plugins，无需 Python；或使用 Install.cmd 自动安装。\n', encoding='utf-8')
    for action, name in [('install','Install.cmd'), ('verify','Verify.cmd'), ('uninstall','Uninstall.cmd')]:
        from tools.build_release_bundle import cmd
        (plugin / name).write_bytes(cmd(action))
    source = BUNDLE / '源码'; prepare(ROOT, source)
    (BUNDLE / 'README.md').write_text('''# Lord of the rings online_CN汉化包

本地发布候选 0.1.0-preview；尚未上传 GitHub。

| 目录／附件 | 用途 |
|---|---|
| [汉化包](汉化包/安装使用说明.md) | 选择自己的游戏主目录，校验版本、备份并安装；包含详细还原和更新说明 |
| [LotroZhItemEnglish-0.1.4](LotroZhItemEnglish-0.1.4/使用说明.md) | 可选的独立物品英文名查询插件；手动复制可不装 Python |
| [源码](源码/README.md) | GitHub 仓库内容，开发测试代码保留；不含历史测试记录和本机安装收据 |
| SHA256SUMS.txt | 三个压缩附件的实际哈希 |

上传仓库使用“源码”内的内容，Release 分开上传汉化包与插件 ZIP。项目标题保留上述中文名称，仓库名建议 Lord-of-the-rings-online_CN。

不同电脑通过目录选择或 --game-dir 统一处理盘符和安装位置；仍须匹配清单中的英文资源版本。商城暂为英文，译文仍待校对。

已按包内 SHA-256 重建验证五个完整 DAT；本轮未部署到游戏。字体字形和其他资源的公开分发范围及项目许可证尚需维护者确定，详见 来源与许可.md。
''', encoding='utf-8')
    shutil.copyfile(ROOT / 'THIRD_PARTY_NOTICES.md', BUNDLE / '来源与许可.md')
    notice = BUNDLE / '来源与许可.md'
    notice.write_text(notice.read_text(encoding='utf-8').replace('[发布清单](docs/RELEASING.md)',
                       '[发布步骤](发布步骤.md)'), encoding='utf-8')
    shutil.copyfile(ROOT / 'docs/RELEASING.md', BUNDLE / '发布步骤.md')
    assets = [('汉化包','Lord-of-the-rings-online_CN-0.1.0-preview.zip'),
              ('LotroZhItemEnglish-0.1.4','LotroZhItemEnglish-0.1.4.zip'),
              ('源码','Lord-of-the-rings-online_CN-source-0.1.0-preview.zip')]
    hashes = []
    for folder, filename in assets:
        target = BUNDLE / filename
        print('Creating and verifying:', filename, flush=True)
        archive_tree(BUNDLE / folder, target)
        hashes.append(delta.digest(target) + '  ' + filename)
    (BUNDLE / 'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n', encoding='utf-8')
    print('Release assets ready locally:', BUNDLE, flush=True)


if __name__ == '__main__':
    main()
