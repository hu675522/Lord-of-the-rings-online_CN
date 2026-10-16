"""Restore this audited local test snapshot, retaining live files until verified.

This is a one-snapshot recovery tool, not a general force/ignore-version option.
It accepts only the exact hashes recorded by the runtime difference audit.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from client_patch.full_manager import (archive_names, copy_checked, file_hash,
                                      game_directory, load_plan, require_closed, write_json)


def restore(package=None):
    package = Path(package or ROOT / 'client_patch/full').resolve()
    if not package.is_relative_to((ROOT / 'client_patch').resolve()):
        raise ValueError('Recovery package must belong to this workspace')
    plan = load_plan(package)
    if plan['package_id'] not in {'full-draft-ae9c605a20e9579d', 'full-draft-e93bb5ed8e8cd5c1', 'full-draft-b38987d4c23ab456', 'full-draft-bf681ae09630df99', 'full-draft-1f21b7a124c7059b', 'full-draft-45f998a2ad1f82ea'}:
        raise ValueError('This audit belongs to a different snapshot')
    names = archive_names(plan)
    receipt = json.loads((package / 'installed-receipt.json').read_text(encoding='utf-8'))
    game = game_directory(package, receipt['game_directory'], names=names)
    observed = json.loads((package / 'pre-restore-current-files.json').read_text(encoding='utf-8'))
    audit = json.loads((package / 'runtime-public-resource-audit.json').read_text(encoding='utf-8'))
    if set(observed) != set(names) or set(audit) != set(names):
        raise ValueError('Incomplete archive audit')
    for name, data in audit.items():
        allowed = {'0x2505ba52'} if name == 'client_local_English.dat' else set()
        changed = [r['id'] for r in data['changed_public_resources']]
        if len(set(changed)) != len(changed) or not set(changed) <= allowed:
            raise ValueError('Unexpected public changes')
    if (package / 'operation-journal.json').exists() or (package / 'audited-restore-journal.json').exists():
        raise ValueError('An unfinished operation already exists')
    require_closed()
    stages = []
    moved = []
    journal = package / 'audited-restore-journal.json'
    committed = False
    try:
        if shutil.disk_usage(game).free < sum(a['original_size'] for a in plan['archives']) + 256*1024**2:
            raise ValueError('Not enough staging space')
        for archive in plan['archives']:
            name = archive['name']
            target = game / name
            backup = package / 'backups' / (name + '.original')
            if file_hash(target) != observed[name]['sha256']:
                raise ValueError('Live file changed after audit: ' + name)
            if file_hash(backup) != archive['original_sha256']:
                raise ValueError('Original backup mismatch: ' + name)
            stage = game / (name + '.lotrozh-audited-restore.tmp')
            before = game / (name + '.lotrozh-before-restore.tmp')
            if stage.exists() or before.exists():
                raise ValueError('Unexpected recovery temporary file')
            stages.append((archive, target, stage, before))
            copy_checked(backup, stage, archive['original_sha256'])
            print('Staged verified English original: ' + name, flush=True)
        require_closed()
        write_json(journal, {'game_directory': str(game), 'before': observed,
                             'phase': 'swapping', 'files': [a['name'] for a in plan['archives']]})
        for archive, target, stage, before in stages:
            require_closed()
            if file_hash(target) != observed[archive['name']]['sha256']:
                raise ValueError('Live file changed before swap')
            os.replace(target, before)
            moved.append((archive, target, before))
            os.replace(stage, target)
            if file_hash(target) != archive['original_sha256']:
                raise ValueError('English restore verification failed')
            print('Restored and verified: ' + archive['name'], flush=True)
        verified = {a['name']: {'state': 'original', 'sha256': file_hash(game / a['name'])}
                    for a in plan['archives']}
        if not all(verified[a['name']]['sha256'] == a['original_sha256'] for a in plan['archives']):
            raise ValueError('Final English verification failed')
        write_json(package / 'restore-verification.json', {
            'package_id': plan['package_id'], 'state': 'restored', 'game_directory': str(game),
            'verified_utc': datetime.now(timezone.utc).isoformat(), 'game_files': verified,
            'runtime_difference_audit': 'runtime-public-resource-audit.json'})
        receipt.update(state='restored', updated_utc=datetime.now(timezone.utc).isoformat(),
                       restore_audit='restore-verification.json')
        write_json(package / 'installed-receipt.json', receipt)
        committed = True
    except Exception:
        failures = []
        for archive, target, before in reversed(moved):
            try:
                if file_hash(before) != observed[archive['name']]['sha256']:
                    raise ValueError('Pre-operation file mismatch')
                os.replace(before, target)
            except Exception as error:
                failures.append(str(error))
        if failures:
            raise RuntimeError('Rollback incomplete; keep game closed: ' + '; '.join(failures))
        journal.unlink(missing_ok=True)
        raise
    finally:
        for _, _, stage, _ in stages:
            stage.unlink(missing_ok=True)
    if committed:
        # Old live files are redundant only after all original hashes pass.
        for _, _, before in moved:
            before.unlink()
        journal.unlink()
        print(f'All {len(names)} English originals restored; no runtime snapshot retained.', flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path)
    restore(parser.parse_args().package)
