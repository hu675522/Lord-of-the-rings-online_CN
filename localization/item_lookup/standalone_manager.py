"""Manage ONLY LotroZhItemEnglish files. No DAT/client executable access."""
import argparse
import csv
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write_json(path,value):
    path=Path(path);temp=path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(path)


def require_closed():
    if os.name!='nt':raise ValueError('Installation is supported on Windows only')
    tasklist=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/tasklist.exe'
    result=subprocess.run([str(tasklist),'/FO','CSV','/NH'],capture_output=True,check=True)
    names={row[0].casefold() for row in csv.reader(result.stdout.decode('mbcs').splitlines()) if row}
    if names & {'lotroclient.exe','lotroclient64.exe','lotrolauncher.exe','turbineinvoker.exe'}:
        raise ValueError('Exit LOTRO and its launcher before installing/uninstalling the plugin')


def default_plugins():
    if os.name!='nt':raise ValueError('Specify --plugins-dir for this platform')
    buffer=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,5,None,0,buffer)!=0:
        raise ValueError('Could not locate Windows Documents folder')
    return Path(buffer.value)/'The Lord of the Rings Online/Plugins'


def target_for(plugins,name):
    root=Path(plugins).resolve();rel=Path(name)
    if rel.is_absolute() or rel.drive or '..' in rel.parts:raise ValueError('Unsafe plugin path')
    if name!='LotroZh/LotroZhItemEnglish.plugin' and not name.startswith('LotroZh/ItemEnglish/'):
        raise ValueError('File is outside this plugin')
    if name.startswith('LotroZh/ItemEnglish/') and rel.suffix!='.lua':raise ValueError('Only this plugin Lua payload is allowed')
    target=(root/rel).resolve()
    if not target.is_relative_to(root):raise ValueError('Plugin target escapes directory')
    return target


def verify(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'plugin-manifest.json').read_text(encoding='utf-8'))
    rows=[];seen=set()
    for row in manifest['records']:
        name=row['file']
        if not name.startswith('Plugins/'):raise ValueError('Non-plugin package entry')
        relative=name[len('Plugins/'):];source=target_for(root/'Plugins',relative)
        if source in seen:raise ValueError('Duplicate plugin record')
        seen.add(source)
        if source.stat().st_size!=row['bytes'] or digest(source)!=row['sha256']:
            raise ValueError('Plugin payload checksum mismatch: '+relative)
        rows.append({'target':relative,'sha256':row['sha256'],'source':source})
    if not rows or 'LotroZh/LotroZhItemEnglish.plugin' not in {r['target'] for r in rows}:
        raise ValueError('Missing plugin descriptor')
    return rows


def install(root,plugins):
    root=Path(root).resolve();plugins=Path(plugins).resolve()
    rows=verify(root);require_closed();receipt=root/'installed-receipt.json'
    if receipt.exists() and json.loads(receipt.read_text(encoding='utf-8'))['state'] in {'installed','installing'}:
        raise ValueError('Uninstall this plugin version before reinstalling')
    stages=[];created=[]
    for row in rows:
        target=target_for(plugins,row['target']);stage=target.with_name(target.name+'.itemenglish.tmp')
        if target.exists() or stage.exists():raise ValueError('Existing file preserved: '+row['target'])
        stages.append((row,target,stage))
    state={'state':'installing','plugins_directory':str(plugins),
           'files':[{'target':r['target'],'sha256':r['sha256']} for r in rows],
           'plugin_only':True,'game_archives_modified':False}
    try:
        for row,target,stage in stages:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(row['source'],stage)
            if digest(stage)!=row['sha256']:raise ValueError('Staged plugin checksum mismatch')
        require_closed();write_json(receipt,state)
        for row,target,stage in stages:
            if target.exists():raise ValueError('Plugin target appeared during install')
            stage.replace(target);created.append((row,target))
        if any(digest(target)!=row['sha256'] for row,target in created):raise ValueError('Installed checksum mismatch')
        state['state']='installed';write_json(receipt,state)
    except Exception:
        failures=[]
        for row,target in reversed(created):
            if target.exists():
                if digest(target)!=row['sha256']:failures.append(row['target'])
                else:target.unlink()
        if failures:raise RuntimeError('Some files changed; retain receipt: '+', '.join(failures))
        if receipt.exists():state['state']='not-installed';write_json(receipt,state)
        raise
    finally:
        for _,_,stage in stages:stage.unlink(missing_ok=True)
    return len(rows)


def uninstall(root):
    root=Path(root).resolve();receipt=root/'installed-receipt.json'
    state=json.loads(receipt.read_text(encoding='utf-8'));require_closed()
    if state['state'] not in {'installed','installing'}:raise ValueError('Plugin is not installed by this package')
    plugins=Path(state['plugins_directory']);targets=[];seen=set()
    for row in state['files']:
        target=target_for(plugins,row['target'])
        if target in seen:raise ValueError('Duplicate receipt target')
        seen.add(target)
        if target.exists() and digest(target)!=row['sha256']:raise ValueError('Changed file preserved: '+row['target'])
        targets.append(target)
    for target in targets:target.unlink(missing_ok=True)
    state['state']='uninstalled';write_json(receipt,state)
    return len(targets)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',default='verify',choices=['verify','install','uninstall'])
    parser.add_argument('--plugins-dir',type=Path)
    args=parser.parse_args();root=Path(__file__).resolve().parent
    try:
        count=len(verify(root)) if args.command=='verify' else install(root,args.plugins_dir or default_plugins()) if args.command=='install' else uninstall(root)
        print(json.dumps({'action':args.command,'plugin_files_verified':count,'plugin_only':True,'game_archives_modified':False},indent=2))
    except (OSError,ValueError,RuntimeError,KeyError,subprocess.SubprocessError) as error:
        print('Stopped: '+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
