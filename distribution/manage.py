"""Portable LOTRO Chinese difference package manager (Python 3.11+)."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

try:
    from . import delta
    from client_patch import full_manager as core
except ImportError:
    import delta
    import full_manager as core


def load(root):
    root = Path(root).resolve()
    plan = core.load_plan(root)
    if plan.get('distribution_format') != 'sha256-block-delta-v1':
        raise ValueError('Not a distributable difference package')
    for row in plan['archives']:
        if row['delta'] != 'payload/' + row['name'] + '.zip':
            raise ValueError('Unexpected difference payload path')
        if (root / row['delta']).resolve().parent != (root / 'payload').resolve():
            raise ValueError('Difference payload escapes package')
    return plan


def verify(root, plan):
    for row in plan['archives']:
        if delta.digest(root / row['delta']) != row['delta_sha256']:
            raise ValueError('Difference package damaged: ' + row['name'])
        print('Verified difference:', row['name'], flush=True)


def choose_game(root, provided):
    if provided:
        return Path(provided).expanduser().resolve()
    receipt = root / 'installed-receipt.json'
    initial = ''
    if receipt.exists():
        initial = json.loads(receipt.read_text(encoding='utf-8')).get('game_directory', '')
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        tk = None
    selected = None
    if tk is not None:
        try:
            window = tk.Tk(); window.withdraw()
            try:
                selected = filedialog.askdirectory(title='选择 LOTRO 游戏主目录（包含 client_local_English.dat）', initialdir=initial or None)
            finally:
                window.destroy()
        except tk.TclError:
            selected = None
    if selected is None:
        selected = input('请输入 LOTRO 游戏主目录完整路径（留空取消）：').strip().strip('"')
    if not selected:
        raise ValueError('Cancelled; no game files modified')
    return Path(selected).expanduser().resolve()


def prepare(root, plan, game):
    core.require_closed()
    current = core.inspect_game(root, plan, game)
    for row in plan['archives']:
        candidate = root / row['candidate']
        if candidate.exists():
            if candidate.stat().st_size != row['candidate_size'] or delta.digest(candidate) != row['patched_sha256']:
                raise ValueError('Existing candidate damaged; no overwrite: ' + row['name'])
        elif current[row['name']]['state'] != 'original':
            raise ValueError('English source mismatch; update/reinstall supported English version first: ' + row['name'])
    # Include future backups and transaction staging, even before generating work/.
    missing_candidates = sum(r['candidate_size'] for r in plan['archives'] if not (root / r['candidate']).exists())
    missing_backups = sum(r['original_size'] for r in plan['archives'] if not core.backup_path(root, r['name']).exists())
    stages = sum(r['candidate_size'] for r in plan['archives'])
    if root.drive.casefold() == game.drive.casefold():
        if shutil.disk_usage(root).free < missing_candidates + missing_backups + stages + 512 * 1024**2:
            raise ValueError('Insufficient space for candidates, English backups and staging')
    elif (shutil.disk_usage(root).free < missing_candidates + missing_backups + 512 * 1024**2 or
          shutil.disk_usage(game).free < stages + 512 * 1024**2):
        raise ValueError('Insufficient package/game disk space')
    for row in plan['archives']:
        candidate = root / row['candidate']
        if not candidate.exists():
            core.require_closed()
            print('Generating candidate:', row['name'], flush=True)
            delta.apply(game / row['name'], root / row['delta'], candidate, row)
    core.require_closed()


def cleanup(root, plan, game):
    core.require_closed()
    receipt = json.loads((root / 'installed-receipt.json').read_text(encoding='utf-8'))
    if receipt['state'] != 'restored' or Path(receipt['game_directory']).resolve() != game:
        raise ValueError('Restore this package before cleanup')
    if (root / 'operation-journal.json').exists():
        raise ValueError('Recover unfinished operation before cleanup')
    if any(row['state'] != 'original' for row in core.inspect_game(root, plan, game).values()):
        raise ValueError('Current English resources do not match; preserve backups')
    targets = []
    for row in plan['archives']:
        for file, expected in ((core.backup_path(root, row['name']), row['original_sha256']),
                               (root / row['candidate'], row['patched_sha256'])):
            if not file.resolve().is_relative_to(root) or file.is_symlink():
                raise ValueError('Cleanup path escapes package')
            if file.exists():
                if delta.digest(file) != expected:
                    raise ValueError('Cleanup file changed; preserve for inspection')
                targets.append(file)
    core.require_closed()
    for file in targets:
        file.unlink()
    core.write_json(root / 'cleanup-receipt.json', {'state': 'restored-and-cleaned', 'removed_files': len(targets)})
    print('English verified; local backups and candidates removed. Difference payloads retained.')


def run(root, action, provided=None):
    root = Path(root).resolve(); plan = load(root); verify(root, plan)
    if action == 'verify':
        return
    game = core.game_directory(root, choose_game(root, provided), core.archive_names(plan))
    if action == 'check':
        print(json.dumps(core.inspect_game(root, plan, game), ensure_ascii=False, indent=2))
    elif action == 'install':
        if (root / 'operation-journal.json').exists():
            raise ValueError('Unfinished operation: run recover first')
        prepare(root, plan, game)
        core.transition(root, plan, game)
    elif action == 'restore':
        core.transition(root, plan, game, restoring=True)
    elif action == 'recover':
        core.recover(root, plan, game)
    elif action == 'cleanup':
        cleanup(root, plan, game)


def main():
    if sys.version_info < (3, 11):
        print('Python 3.11+ required (recommended: 3.12).', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'check', 'install', 'restore', 'recover', 'cleanup'))
    parser.add_argument('--game-dir', type=Path)
    args = parser.parse_args()
    try:
        run(Path(__file__).resolve().parent, args.action, args.game_dir)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print('停止 / Stopped: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
