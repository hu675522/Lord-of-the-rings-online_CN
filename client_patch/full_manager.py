"""Portable full-candidate verification, guarded installation and recovery.

Copied into a built package as manage.py. Default package policy denies installs.
All game writes require an explicit command, matching hashes and closed clients.
"""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

NAMES=('client_local_English.dat','client_surface.dat','client_surface_aux_1.datx','client_surface_aux_2.datx')
PROCESSES={'lotroclient.exe','lotroclient64.exe','lotrolauncher.exe','turbineinvoker.exe','turbinelauncher.exe'}


def archive_names(plan):
    return tuple(a['name'] for a in plan['archives'])


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda:file.read(16*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def write_json(path,data):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)


def require_closed():
    if os.name!='nt':raise RuntimeError('真实安装和还原只支持 Windows')
    tasklist=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/tasklist.exe'
    result=subprocess.run([str(tasklist),'/FO','CSV','/NH'],capture_output=True,check=True)
    running={row[0].casefold() for row in csv.reader(result.stdout.decode('mbcs').splitlines()) if row}
    found=running&PROCESSES
    if found:raise RuntimeError('请退出游戏和启动器：'+', '.join(sorted(found)))


def load_plan(root):
    root=Path(root).resolve()
    plan=json.loads((root/'install-plan.json').read_text(encoding='utf-8'))
    if plan.get('schema') not in (2,3) or not plan.get('candidate_build_complete') or not plan.get('all_workspace_checks_passed'):
        raise ValueError('全量候选计划尚未通过副本校验')
    archives=plan['archives']
    names=archive_names(plan)
    expected=set(NAMES)|({'client_general.dat'} if plan['schema']==3 else set())
    if len(names)!=len(expected) or set(names)!=expected:raise ValueError('资源组与计划版本指定的文件不匹配')
    for archive in archives:
        name=archive['name']
        if archive['candidate']!='work/'+name:raise ValueError('候选路径必须属于包内 work 目录')
        path=(root/archive['candidate']).resolve()
        if not path.is_relative_to(root/'work'):raise ValueError('候选文件路径越界')
        for key in ('original_sha256','patched_sha256'):
            if not re.fullmatch('[0-9a-f]{64}',archive[key]):raise ValueError('无效资源哈希')
    return plan


def verify_package(root,plan):
    root=Path(root).resolve()
    for archive in plan['archives']:
        source=root/archive['candidate']
        if source.stat().st_size!=archive['candidate_size'] or file_hash(source)!=archive['patched_sha256']:
            raise ValueError('候选文件校验失败：'+archive['name'])
        print('候选已核对：'+archive['name'],flush=True)
    return {'candidate_files_verified':len(plan['archives']),'package_id':plan['package_id'],'game_tested':False}


def game_directory(root,directory,names=NAMES):
    root=Path(root).resolve();directory=Path(directory).resolve()
    if root==directory or root in directory.parents or directory in root.parents:
        raise ValueError('游戏与补丁包必须位于分开的目录')
    for name in names:
        target=directory/name
        if not target.is_file() or target.resolve().parent!=directory:raise ValueError('游戏资源缺失或路径异常：'+name)
    return directory


def inspect_game(root,plan,directory):
    directory=game_directory(root,directory,archive_names(plan));result={}
    for archive in plan['archives']:
        actual=file_hash(directory/archive['name'])
        state='original' if actual==archive['original_sha256'] else 'full_candidate' if actual==archive['patched_sha256'] else 'unknown'
        result[archive['name']]={'state':state,'sha256':actual}
    return result


def backup_path(root,name):return Path(root)/'backups'/(name+'.original')


def rollback_source(root,archive,digest):
    if digest==archive['original_sha256']:return backup_path(root,archive['name'])
    if digest==archive['patched_sha256']:return Path(root)/archive['candidate']
    raise ValueError('回滚哈希不属于这个包')


def copy_checked(source,target,expected):
    shutil.copyfile(source,target)
    if file_hash(target)!=expected:raise ValueError('复制校验失败：'+target.name)


def check_space(root,game,backup_bytes,stage_bytes):
    root=Path(root).resolve();game=Path(game).resolve();margin=256*1024*1024
    same=root.drive.casefold()==game.drive.casefold()
    if same:
        if shutil.disk_usage(game).free<backup_bytes+stage_bytes+margin:raise ValueError('备份和整组暂存空间不足')
    else:
        if shutil.disk_usage(root).free<backup_bytes+margin or shutil.disk_usage(game).free<stage_bytes+margin:
            raise ValueError('备份盘或游戏盘暂存空间不足')


def transition(root,plan,directory,restoring=False):
    root=Path(root).resolve()
    if not restoring:
        policy=root/'deployment-policy.json'
        if not policy.is_file() or json.loads(policy.read_text(encoding='utf-8')).get('deployment_enabled') is not True:
            raise ValueError('暂不部署：此全量候选包的安装开关保持关闭')
    if (root/'operation-journal.json').exists():raise ValueError('存在未完成操作，请先执行 recover')
    require_closed();directory=game_directory(root,directory,archive_names(plan));verify_package(root,plan)
    current=inspect_game(root,plan,directory);actions=[];missing=[]
    for archive in plan['archives']:
        name=archive['name'];before=current[name]
        if before['state']=='unknown':raise ValueError('游戏文件与基线不匹配，可能已更新：'+name)
        backup=backup_path(root,name)
        if backup.exists():
            if file_hash(backup)!=archive['original_sha256']:raise ValueError('原始备份损坏：'+name)
        elif restoring or before['state']!='original':raise ValueError('缺少可用的英文备份：'+name)
        else:missing.append(archive)
        desired=archive['original_sha256'] if restoring else archive['patched_sha256']
        if before['sha256']!=desired:
            actions.append({'archive':archive,'target':directory/name,'before':before['sha256'],'expected':desired,
                            'source':backup if restoring else root/archive['candidate']})
    check_space(root,directory,sum(a['original_size'] for a in missing),sum(a['source'].stat().st_size for a in actions))
    for archive in missing:
        target=backup_path(root,archive['name']);target.parent.mkdir(parents=True,exist_ok=True)
        if file_hash(directory/archive['name'])!=archive['original_sha256']:raise ValueError('备份前游戏文件发生变化')
        temporary=target.with_suffix(target.suffix+'.tmp')
        copy_checked(directory/archive['name'],temporary,archive['original_sha256']);temporary.replace(target)
        print('英文备份已核对：'+archive['name'],flush=True)
    stages=[];changed=[];journal=root/'operation-journal.json'
    try:
        for action in actions:
            stage=action['target'].with_name(action['target'].name+'.lotrozh-'+uuid.uuid4().hex+'.tmp')
            stages.append(stage);action['stage']=stage
            copy_checked(action['source'],stage,action['expected'])
        require_closed()
        write_json(journal,{'package_id':plan['package_id'],'game_directory':str(directory),
            'before':{a['name']:current[a['name']]['sha256'] for a in plan['archives']}})
        for action in actions:
            require_closed()
            if file_hash(action['target'])!=action['before']:raise ValueError('暂存期间游戏文件发生变化')
            os.replace(action['stage'],action['target']);changed.append(action)
            if file_hash(action['target'])!=action['expected']:raise ValueError('替换后哈希不匹配')
            print('已核对：'+action['target'].name,flush=True)
        write_json(root/'installed-receipt.json',{'package_id':plan['package_id'],'game_directory':str(directory),
            'state':'restored' if restoring else 'installed-for-testing','updated_utc':datetime.now(timezone.utc).isoformat(),
            'game_rendering_verified':False})
        journal.unlink()
    except Exception:
        failures=[]
        for action in reversed(changed):
            temporary=action['target'].with_name(action['target'].name+'.lotrozh-rollback.tmp')
            try:
                copy_checked(rollback_source(root,action['archive'],action['before']),temporary,action['before'])
                os.replace(temporary,action['target'])
            except Exception as error:failures.append(str(error))
        if failures:raise RuntimeError('回滚未完成，保持游戏关闭并执行 recover：'+'; '.join(failures))
        journal.unlink(missing_ok=True)
        raise
    finally:
        for stage in stages:stage.unlink(missing_ok=True)
    print('原始英文资源已还原。' if restoring else '全量候选已安装，游戏显示仍待验证。',flush=True)


def recover(root,plan,directory):
    root=Path(root).resolve();directory=game_directory(root,directory,archive_names(plan));require_closed();verify_package(root,plan)
    path=root/'operation-journal.json';journal=json.loads(path.read_text(encoding='utf-8'))
    if journal['package_id']!=plan['package_id'] or Path(journal['game_directory']).resolve()!=directory:
        raise ValueError('恢复记录不属于此补丁或游戏目录')
    if set(journal['before'])!=set(archive_names(plan)):raise ValueError('恢复记录的资源组异常')
    current=inspect_game(root,plan,directory)
    for archive in plan['archives']:
        name=archive['name'];expected=journal['before'][name]
        source=rollback_source(root,archive,expected)
        if current[name]['state']=='unknown' or file_hash(source)!=expected:raise ValueError('恢复来源或游戏版本不匹配')
    for archive in plan['archives']:
        name=archive['name'];expected=journal['before'][name]
        if current[name]['sha256']==expected:continue
        require_closed();temporary=directory/(name+'.lotrozh-recover.tmp')
        try:
            copy_checked(rollback_source(root,archive,expected),temporary,expected)
            if file_hash(directory/name)!=current[name]['sha256']:raise ValueError('恢复期间游戏文件变化')
            os.replace(temporary,directory/name)
        finally:temporary.unlink(missing_ok=True)
    path.unlink();write_json(root/'installed-receipt.json',{'package_id':plan['package_id'],
        'game_directory':str(directory),'state':'recovered-before-operation','game_rendering_verified':False})
    print('已恢复到中断操作之前的资源状态。',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('verify','check','install','restore','recover'))
    parser.add_argument('--game-dir',type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parent
    try:
        plan=load_plan(root)
        if args.command=='verify':print(json.dumps(verify_package(root,plan),ensure_ascii=False,indent=2))
        elif args.game_dir is None:raise ValueError('请明确提供 --game-dir 游戏目录')
        elif args.command=='check':print(json.dumps(inspect_game(root,plan,args.game_dir),ensure_ascii=False,indent=2))
        elif args.command=='recover':recover(root,plan,args.game_dir)
        else:transition(root,plan,args.game_dir,restoring=args.command=='restore')
    except (OSError,ValueError,RuntimeError,KeyError,subprocess.SubprocessError) as error:
        print('停止：'+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
