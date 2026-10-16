"""Hash-bound installation/restore of explicit per-test extra files.

The DAT manager remains responsible for resource archives. This transaction
handles only the pinned client executable and the named item-lookup plugin.
"""
from pathlib import Path
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from client_patch.full_manager import file_hash,copy_checked,write_json,require_closed


def target_for(row,game,plugins):
    name=row['target'];rel=Path(name)
    if rel.is_absolute() or rel.drive or '..' in rel.parts:raise ValueError('Unsafe extra target')
    if row['root']=='game':
        if name!='x64/lotroclient64.exe':raise ValueError('Unapproved game extra')
        root=game
    elif row['root']=='plugins':
        if name not in {'LotroZhItemEnglish.plugin','LotroZh/LotroZhItemEnglish.plugin'} and not name.startswith('LotroZh/ItemEnglish/'):
            raise ValueError('Unapproved plugin extra')
        root=plugins
    else:raise ValueError('Unapproved root')
    target=(root/rel).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('Extra target outside root')
    return target


def install(package,game,plugins):
    package=Path(package).resolve();game=Path(game).resolve();plugins=Path(plugins).resolve()
    plan=json.loads((package/'extras-plan.json').read_text(encoding='utf-8'))
    if not plan.get('authorized_for_this_test'):raise ValueError('Test authorization missing')
    journal=package/'extras-journal.json'
    if journal.exists() or (package/'extras-receipt.json').exists():raise ValueError('Inspect previous extra operation first')
    require_closed();actions=[];seen=set()
    for row in plan['files']:
        target=target_for(row,game,plugins)
        if target in seen:raise ValueError('Duplicate target')
        seen.add(target)
        source=(package/row['candidate']).resolve()
        if not source.is_relative_to(package/'extras') or file_hash(source)!=row['sha256']:
            raise ValueError('Extra candidate mismatch')
        before=file_hash(target) if target.exists() else None
        if before!=row['before_sha256']:raise ValueError('Extra target changed: '+row['target'])
        backup=package/'backups/extras'/row['root']/row['target']
        if before:
            backup.parent.mkdir(parents=True,exist_ok=True)
            copy_checked(target,backup,before)
        stage=target.with_name(target.name+'.lotrozh-extra.tmp')
        if stage.exists():raise ValueError('Unexpected extra staging file')
        actions.append({'row':row,'source':source,'target':target,'backup':backup,'stage':stage,'before':before})
    changed=[]
    try:
        for a in actions:
            a['target'].parent.mkdir(parents=True,exist_ok=True)
            copy_checked(a['source'],a['stage'],a['row']['sha256'])
        require_closed()
        write_json(journal,{'game_directory':str(game),'plugins_directory':str(plugins),'files':plan['files']})
        for index,a in enumerate(actions):
            if index%50==0 or a['row']['root']=='game':require_closed()
            if (file_hash(a['target']) if a['target'].exists() else None)!=a['before']:
                raise ValueError('Extra target changed before replacement')
            os.replace(a['stage'],a['target']);changed.append(a)
            if file_hash(a['target'])!=a['row']['sha256']:raise ValueError('Installed extra mismatch')
        for a in actions:
            if file_hash(a['target'])!=a['row']['sha256']:raise ValueError('Final extra verification failed')
        write_json(package/'extras-receipt.json',{'state':'installed-for-testing','game_directory':str(game),
            'plugins_directory':str(plugins),'files_verified':len(actions),'files':plan['files']})
        journal.unlink()
    except Exception:
        failures=[]
        for a in reversed(changed):
            try:
                if a['before']:
                    copy_checked(a['backup'],a['stage'],a['before']);os.replace(a['stage'],a['target'])
                else:a['target'].unlink()
            except Exception as e:failures.append(str(e))
        if failures:raise RuntimeError('Extra rollback incomplete; retain journal: '+'; '.join(failures))
        journal.unlink(missing_ok=True)
        raise
    finally:
        for a in actions:a['stage'].unlink(missing_ok=True)
    return len(actions)


def restore(package):
    package=Path(package).resolve()
    receipt=json.loads((package/'extras-receipt.json').read_text(encoding='utf-8'))
    if receipt['state']!='installed-for-testing':raise ValueError('Extras are not installed')
    game=Path(receipt['game_directory']);plugins=Path(receipt['plugins_directory'])
    require_closed()
    # Verify the whole group before touching any file, including all backups.
    for row in receipt['files']:
        target=target_for(row,game,plugins)
        if file_hash(target)!=row['sha256']:raise ValueError('Installed extra changed: '+row['target'])
        if row['before_sha256']:
            backup=package/'backups/extras'/row['root']/row['target']
            if file_hash(backup)!=row['before_sha256']:raise ValueError('Extra backup mismatch')
    for index,row in enumerate(receipt['files']):
        if index%50==0 or row['root']=='game':require_closed()
        target=target_for(row,game,plugins)
        if row['before_sha256']:
            temporary=target.with_name(target.name+'.lotrozh-extra-restore.tmp')
            try:
                copy_checked(package/'backups/extras'/row['root']/row['target'],temporary,row['before_sha256'])
                os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
        else:target.unlink()
    receipt['state']='restored';write_json(package/'extras-receipt.json',receipt)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['restore'])
    p.add_argument('--package',type=Path,required=True);args=p.parse_args();restore(args.package)
