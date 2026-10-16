"""Build a local distributable difference bundle; never install or publish."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from distribution import delta
from client_patch.full_manager import load_plan

TITLE = 'Lord of the rings online_CN汉化包'


def cmd(action):
    return ('@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\n'
            'where py >nul 2>nul\r\nif errorlevel 1 (\r\n'
            '  python "%~dp0manage.py" ' + action + '\r\n'
            ') else (\r\n  py -3 "%~dp0manage.py" ' + action + '\r\n)\r\npause\r\n').encode('utf-8')


def build(package, game, output):
    package, game, output = map(lambda p: Path(p).resolve(), (package, game, output))
    if not output.is_relative_to(ROOT / 'release') or output.exists():
        raise ValueError('Use a new release/ destination')
    original = load_plan(package)
    lang = output / '汉化包'; lang.mkdir(parents=True)
    plan = {k: original[k] for k in ('schema', 'package_id', 'candidate_build_complete',
            'all_workspace_checks_passed', 'counts', 'bilingual_maps', 'archives')}
    plan.update(distribution_format='sha256-block-delta-v1', title=TITLE,
                release_version='0.1.0-preview', component='DAT localization only', plugin_payloads_included=False)
    for row in plan['archives']:
        source = game / row['name']; candidate = package / row['candidate']
        if delta.digest(source) != row['original_sha256'] or delta.digest(candidate) != row['patched_sha256']:
            raise ValueError('Source/candidate checksum mismatch')
        row['delta'] = 'payload/' + row['name'] + '.zip'
        target = lang / row['delta']
        print('Building compressed difference:', row['name'], flush=True)
        meta = delta.build(source, candidate, target)
        for key in ('original_size', 'candidate_size', 'original_sha256', 'patched_sha256'):
            if meta[key] != row[key]:
                raise ValueError('Difference source changed during build')
        row['delta_sha256'] = delta.digest(target)
        # Independently reconstruct the actual full-size file, verify its final
        # SHA and remove only this temporary reconstruction (not the source).
        verify_target = package / 'delta-verification' / row['name']
        delta.apply(source, target, verify_target, row)
        verify_target.unlink()
        print('Full-size reconstruction verified:', row['name'], flush=True)
    (lang / 'install-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (lang / 'deployment-policy.json').write_text(json.dumps({'deployment_enabled': True,
        'reason': 'Explicit user install command required; exact supported source SHA-256 enforced.'}, indent=2), encoding='utf-8')
    for source, name in [('distribution/manage.py', 'manage.py'), ('distribution/delta.py', 'delta.py'),
                         ('client_patch/full_manager.py', 'full_manager.py')]:
        shutil.copyfile(ROOT / source, lang / name)
    for action, name in [('verify', '01_校验补丁.cmd'), ('check', '02_检查游戏版本.cmd'),
                         ('install', '03_安装汉化.cmd'), ('restore', '04_还原英文.cmd'),
                         ('recover', '05_中断恢复.cmd'), ('cleanup', '06_还原后清理备份.cmd')]:
        (lang / name).write_bytes(cmd(action))
    shutil.copyfile(ROOT / 'docs/INSTALL.md', lang / '安装使用说明.md')
    (lang / 'README.md').write_text('# '+TITLE+'\n\n先阅读 [安装使用说明](安装使用说明.md)。\n'
        '解压后依次运行 01、02、03。安装时选择你自己的游戏主目录。\n'
        '需要 Windows 和 Python 3.11+（建议 3.12，包含 Tk）。无需翻译模型、原生 DLL 或英文名插件。\n', encoding='utf-8')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'release' / TITLE)
    args = parser.parse_args()
    print(build(args.package, args.game_dir, args.output))


if __name__ == '__main__':
    main()
