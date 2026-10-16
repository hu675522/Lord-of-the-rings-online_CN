"""Package the verified discovery layout and Lua files; never install."""
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from localization.item_lookup.layout import validate_layout


def main():
    folder=ROOT/'localization/item_lookup/generated'
    layout=validate_layout(folder)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    validation=json.loads((folder/'validation.json').read_text(encoding='utf-8'))
    if not validation.get('entry_loaded_from_descriptor') or validation.get('version')!=layout['version']:
        raise ValueError('Verify Lua and descriptor before packaging')
    if not (validation.get('weak_registry_gc_retains_window_controls_and_command') and
            validation.get('hide_reopen_reset_after_gc_verified')):
        raise ValueError('Verify UI lifetime and reopen behavior before packaging')
    for check in ('screenshot_item_exact_match_verified','cached_shard_registry_verified',
                  'shard_load_error_and_retry_verified','module_scope_registry_verified','dictionary_ascii_source_verified'):
        if validation.get(check) is not True:raise ValueError('Verify lookup regression before packaging: '+check)
    version=layout['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Unexpected version')
    target=folder/f'LotroZhItemEnglish-{version}.zip'
    readme=f'''# LotroZhItemEnglish {version}（独立插件）

此包只安装／卸载用户文档 Plugins 中的英文名插件。无需汉化 DAT、模型、数据库或原生 DLL；不会安装、还原或备份游戏资源。
游戏界面默认英文，使其不依赖中文字体补丁。插件仍接受中文名称并提供英文候选；同名时请核对候选。

需要 Python 3.11+（建议 3.12）。先退出游戏与启动器，在本包目录执行：

```powershell
py -3 manage.py verify
py -3 manage.py install
```

默认通过 Windows 文档已知文件夹定位 Plugins，支持重定向文档。自定义路径可使用 `--plugins-dir '完整的 Plugins 目录'`。
也可双击 Install.cmd；若提示文件已存在，请先从旧插件包卸载旧版，不要覆盖其他插件。

进游戏后逐条输入 `/plugins refresh`、`/plugins load LotroZhItemEnglish`。
把物品拖入方框，或手动输入中文名后点 Find。选中英文 Ctrl+A、Ctrl+C，再到拍卖行 Ctrl+V。
`/zhenitem` 显示窗口，`/zhenitem hide` 隐藏，`/zhenitem reset` 重置位置，`/zhenitem debug` 输出最近一次查询的字节和词库诊断。

卸载前退出游戏，保留本解压目录及 installed-receipt.json，再执行 `py -3 manage.py uninstall` 或双击 Uninstall.cmd。
卸载会逐项核对收据，只移除本包安装的文件；文件被修改时停止并保留它们。它不会还原或删除汉化 DAT。

manual-install: copy only the Plugins/LotroZh folder into the game's Documents Plugins directory, preserving its structure.
手动复制不生成安装收据，需要自行移除此插件的描述文件及 ItemEnglish 目录，保留作者目录内的其他插件。

词库来自汉化名称对照，包含同名和非物品名称，不能把条目数视为可交易物品数。离线检查通过不代替真实游戏测试。
'''
    extras={'manage.py':(ROOT/'localization/item_lookup/standalone_manager.py').read_bytes(),
            'plugin-manifest.json':(folder/'manifest.json').read_bytes(),
            'validation.json':(folder/'validation.json').read_bytes(),'README.md':readme.encode('utf-8')}
    for action,filename in [('install','Install.cmd'),('uninstall','Uninstall.cmd'),('verify','Verify.cmd')]:
        extras[filename]=('@echo off\r\nchcp 65001 >nul\r\npy -3 "%~dp0manage.py" '+action+'\r\npause\r\n').encode('utf-8')
    seen=set()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for record in manifest['records']:
            file=(folder/record['file']).resolve()
            if not file.is_relative_to((folder/'Plugins').resolve()) or file in seen:
                raise ValueError('Unsafe or duplicate plugin record')
            seen.add(file);raw=file.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Plugin export changed')
            archive.writestr(record['file'],raw)
        for name,raw in extras.items():archive.writestr(name,raw)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP integrity failed')
        if set(archive.namelist())!=({r['file'] for r in manifest['records']}|set(extras)):
            raise ValueError('ZIP file set mismatch')
        for row in manifest['records']:
            if hashlib.sha256(archive.read(row['file'])).hexdigest()!=row['sha256']:
                raise ValueError('ZIP entry mismatch')
        for name,raw in extras.items():
            if archive.read(name)!=raw:raise ValueError('Standalone manager entry mismatch')
    report={'file':target.name,'version':version,'bytes':target.stat().st_size,
            'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'descriptor':layout['descriptor'],'files':len(seen),'installed':False,
            'package_files':len(seen)+len(extras),'component':'standalone item-name plugin',
            'game_archives_included':False,'game_tested':False,'all_manifest_files_verified':True,'zip_entries_verified':True}
    (folder/'package.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
