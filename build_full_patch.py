"""Build a separate full DAT candidate package from verified local backups.

Never opens the live game for writing. Large packs are streamed into work copies.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'client_patch/full'
SOURCE=ROOT/'localization/full'
BACKUPS=ROOT/'client_patch/backups'
sys.path.insert(0,str(ROOT))
from client_patch.full_manager import file_hash,write_json,NAMES
from lotro_zh.dat_reader import DatReader
from lotro_zh.text_resource import TextResource
from lotro_zh.font_resource import BitmapFont,alpha_texture
from tools.verify_artifact_files import verify_manifest
from localization.original_sources import original_archive
from lotro_zh.map_resource import jpeg_texture
from localization.maps.verify_maps import load_payloads


def payload_hash(raw):return hashlib.sha256(raw).hexdigest()


def write_package_docs(out,plan):
    size=sum(a['candidate_size'] for a in plan['archives'])
    text=f'''# 全量 DAT 验证候选（未部署）

本包已将 {plan['counts']['changed_fragments']:,} 个译文片段及配套字体封装为完整 DAT 候选。
本包只包含游戏 DAT 汉化资源及字体／地图，不包含 LotroZhItemEnglish 插件；安装与还原不会访问用户文档 Plugins。插件由独立包单独安装和卸载。
候选 {len(plan['archives'])} 个文件合计 {size:,} 字节（约 {size/1024**3:.2f} GiB），包标识 `{plan['package_id']}`。
译文主要为机器初稿，完整游戏显示与人工校对尚未完成。

## 现在可运行的只读检查

需要 Python 3.12；从本目录执行，不需要模型、CUDA 或原生 DLL：

```powershell
py -3.12 manage.py verify
py -3.12 manage.py check --game-dir 'D:\\Program Files\\StandingStoneGames\\The Lord of the Rings Online'
```

`verify` 核对计划内全部候选文件。`check` 对实际游戏文件重新计算哈希，输出 `original`、`full_candidate` 或 `unknown`。
路径仅是示例，必须指向本机实际目录。任何 `unknown` 都需要先检查版本，不能安装跨版本文件。
`manage.cmd` 无参数双击时仅执行 verify，不安装。

## 安装与还原入口

安装命令已经实现，但 `deployment-policy.json` 目前保持关闭；本次构建没有授权修改游戏。
后续经用户明确同意并退出游戏及启动器后，才安排一次实际安装验证。不要自行改开关绕过此状态。

```text
py -3.12 manage.py install --game-dir <实际游戏目录>
py -3.12 manage.py restore --game-dir <实际游戏目录>
py -3.12 manage.py recover --game-dir <实际游戏目录>
```

上面的尖括号是占位说明，不是可以直接粘贴的 PowerShell 命令。install 建立本包的英文 backups，整组暂存后替换；
restore 使用同一包的已验证备份还原。recover 用于处理 operation-journal.json 记录的中断操作，恢复到操作前状态。
还原和中断恢复允许在安装开关关闭时进行，但仍需匹配版本、完整候选、可用备份和已退出的游戏。
单文件替换是原子的，整个资源组依赖回滚，不能保证突然断电后无需 recover。

## 目录与空间

- work/：计划指定的全部候选文件，安装与恢复前都需要保留。
- install-plan.json：便携相对路径、原始与候选哈希。
- manage.py／manage.cmd：不绑定开发机 Python 路径。
- backups/：首次真实安装时创建的英文原件，不随本次构建重复打包。
- build-validation.json：独立读取候选资源的验证记录。
- installation-simulation.json：完整大小的工作区安装／还原测试记录（测试完成后生成）。
- tools/、build-data/：本机构建辅助资料，不是普通玩家安装依赖，也不代表已获准对外分发。

首次安装还需要英文备份空间和游戏磁盘上整组暂存的空间；安装器按实际文件大小检查，预留 256 MiB 余量。
包目录与游戏目录必须分开。游戏已经更新或与清单不匹配时，安装／还原都会停止。

本包仅在本机工作区构建，尚未发布 GitHub；完整游戏资源与第三方库的公开分发范围仍待确认。
'''
    (out/'README.md').write_text(text,encoding='utf-8')
    (out/'manage.cmd').write_text('@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\nif "%~1"=="" (\r\n  py -3.12 "%~dp0manage.py" verify\r\n  pause\r\n) else (\r\n  py -3.12 "%~dp0manage.py" %*\r\n)\r\n',encoding='utf-8')


def write_pack(path,rows,count):
    """Each row is (unsigned resource id, binary payload)."""
    expected={};temporary=path.with_suffix('.building')
    with temporary.open('wb') as file:
        file.write(b'LTZHPAK1'+struct.pack('<I',count))
        for index,(rid,raw) in enumerate(rows,1):
            if rid in expected or len(raw)<4 or int.from_bytes(raw[:4],'little')!=rid:raise ValueError('Invalid/duplicate pack resource')
            digest=hashlib.sha256(raw).digest()
            file.write(struct.pack('<II',rid,len(raw))+digest+raw)
            expected[rid]=digest.hex()
            if index%25000==0:print('Packed resources:',index,'/',count,flush=True)
        if len(expected)!=count:raise ValueError('Pack resource count mismatch')
    temporary.replace(path)
    return expected


def locations(stack,paths):
    result={}
    for path in paths:
        reader=stack.enter_context(DatReader(path))
        for entry in reader.entries():
            # Each extent has its own 0xFF internal metadata records. Public
            # resource IDs, unlike these volume-local records, must be unique.
            if entry.resource_id in result and entry.resource_id<0xff000000:
                raise ValueError('Duplicate public resource id across archive group')
            result[entry.resource_id]=(reader,entry)
    return result


def verify_group(original_paths,candidate_paths,expected):
    with ExitStack() as stack:
        original=locations(stack,original_paths);candidate=locations(stack,candidate_paths)
        old_ids={rid for rid in original if rid<0xff000000};new_ids={rid for rid in candidate if rid<0xff000000}
        if old_ids!=new_ids:raise ValueError('Public resource ID set changed')
        for index,(rid,digest) in enumerate(expected.items(),1):
            reader,entry=candidate[rid];raw=reader.content(entry)
            if payload_hash(raw)!=digest:raise ValueError('Candidate payload mismatch: '+hex(rid))
            if rid>>24==0x25:
                if TextResource.parse(raw).serialize()!=raw:raise ValueError('Text candidate roundtrip mismatch')
            elif rid>>24==0x42:
                if BitmapFont.parse(raw).serialize()!=raw:raise ValueError('Font candidate roundtrip mismatch')
            elif rid>>24==0x41:
                if struct.unpack_from('<I',raw,16)[0]==500:jpeg_texture(raw)
                else:alpha_texture(raw)
            if index%50000==0:print('Verified replacement resources:',index,flush=True)
        choices=sorted(rid for rid,(_,e) in original.items() if rid not in expected and rid>>24 not in (0x78,0xff) and 4<=e.size<=4*1024*1024)
        samples=[choices[i*len(choices)//min(512,len(choices))] for i in range(min(512,len(choices)))]
        for rid in samples:
            old_reader,old_entry=original[rid];new_reader,new_entry=candidate[rid]
            if payload_hash(old_reader.content(old_entry,validate_identifier=False))!=payload_hash(new_reader.content(new_entry,validate_identifier=False)):
                raise ValueError('Untouched resource sample changed')
        return {'replacement_resources_verified':len(expected),'public_resource_ids':len(old_ids),
                'public_resource_id_set_unchanged':True,'untouched_samples_verified':len(samples)}


def runtime_source_snapshot(path,archives,source_digest,map_digest):
    """Accept only this separately audited, exact local runtime snapshot."""
    from tools.audit_window_test_source import CURRENT_ARCHIVES,CACHE_ID,CACHE_HASH
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT/'artifacts'):raise ValueError('Runtime source audit must belong to workspace artifacts')
    audit=json.loads(path.read_text(encoding='utf-8'))
    if (audit.get('kind')!='exact-english-runtime-window-test' or
        audit.get('source_manifest_sha256')!=source_digest or audit.get('map_manifest_sha256')!=map_digest or
        audit.get('text_resources_checked')!=282190 or audit.get('matching_text_resources')!=282189 or
        audit.get('font_map_source_resources_checked')!=361 or audit.get('exclude_resource_ids')!=[CACHE_ID] or
        audit.get('all_other_catalog_text_matches') is not True or audit.get('public_resources')!=311966):
        raise ValueError('Incomplete or stale runtime source audit')
    changes=audit.get('changed_text_resources',[])
    if (len(changes)!=1 or int(changes[0]['id'],16)!=CACHE_ID or changes[0]['current_sha256']!=CACHE_HASH or
        changes[0]['previous_sha256']!='6dac59bc95ca58d6c79357f5e79c830e9ae998ddfd7623fb6fa920e52fd74614'):
        raise ValueError('Unexpected runtime text changes')
    if set(audit['source_archives'])!=set(archives):raise ValueError('Runtime snapshot archive set mismatch')
    for name,row in audit['source_archives'].items():
        old=archives[name]
        if (row['previous_sha256']!=old['original_sha256'] or row['original_sha256']!=CURRENT_ARCHIVES[name]
            or row['original_size']!=old['original_size']):raise ValueError('Unexpected runtime source identity')
    return audit


def build(map_manifest=None,runtime_audit_path=None):
    started=time.monotonic();OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'install-plan.json').exists():raise ValueError('Existing full package preserved; inspect it before rebuilding')
    print('Checking artifact file hashes',flush=True);verify_manifest(SOURCE/'manifest.json')
    source_manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))
    source_digest=file_hash(SOURCE/'manifest.json')
    map_digest=None;map_payloads=[]
    if map_manifest:
        _,map_payloads=load_payloads(map_manifest,218)
        map_digest=file_hash(map_manifest)
    baseline=json.loads((ROOT/'client_patch/package/install-plan.json').read_text(encoding='utf-8'))
    archives={a['name']:a for a in baseline['archives']}
    if set(archives)!=set(NAMES):raise ValueError('Original backup plan does not contain complete group')
    fonts=json.loads((SOURCE/'fonts/manifest.json').read_text(encoding='utf-8'))
    general_records={r['id']:r for r in fonts['records'] if r['group']=='client_general.dat'}
    names=NAMES
    if general_records:
        info=json.loads((ROOT/'data/original-archives.json').read_text(encoding='utf-8'))['archives']['client_general.dat']
        archives['client_general.dat']={'original_sha256':info['sha256'],'original_size':info['bytes']}
        names=NAMES+('client_general.dat',)
    runtime_audit=None;excluded=set();runtime_digest=None
    if runtime_audit_path:
        runtime_audit=runtime_source_snapshot(runtime_audit_path,archives,source_digest,map_digest)
        runtime_digest=file_hash(runtime_audit_path)
        excluded=set(runtime_audit['exclude_resource_ids'])
        for name,row in runtime_audit['source_archives'].items():
            archives[name].update(original_sha256=row['original_sha256'],original_size=row['original_size'])
        shutil.copyfile(runtime_audit_path,OUT/'runtime-source-audit.json')
    package_digest=payload_hash((source_digest+(map_digest or '')+(runtime_digest or '')).encode())
    required=sum(original_archive(n).stat().st_size for n in names)+3*1024**3
    if shutil.disk_usage(OUT).free<required:raise ValueError('Insufficient space for independent candidates')
    for name in names:
        backup=original_archive(name)
        if file_hash(backup)!=archives[name]['original_sha256']:raise ValueError('Original backup hash mismatch: '+name)
        print('Original backup verified:',name,flush=True)
    for folder in ('work','tools','build-data'):(OUT/folder).mkdir(exist_ok=True)
    write_json(OUT/'deployment-policy.json',{'deployment_enabled':False,'reason':'Candidate build only; game installation has not been authorized.'})
    write_json(OUT/'build-state.json',{'phase':'preparing-payloads','source_manifest_sha256':source_digest,'deployment_enabled':False})
    font_records={r['id']:r for r in fonts['records'] if r['id']>>24==0x42 and r['group']=='client_local_English.dat'}
    texture_records={r['id']:r for r in fonts['records'] if r['id']>>24==0x41}
    db=sqlite3.connect((SOURCE/'text-resources.sqlite3').as_uri()+'?mode=ro',uri=True)
    text_count=db.execute('SELECT count(*) FROM resources').fetchone()[0]-len(excluded)
    with DatReader(original_archive('client_local_English.dat')) as original:
        entries={e.resource_id:e for e in original.entries()}
        def text_and_fonts():
            for index,(rid,source_sha,target_sha,raw) in enumerate(db.execute('SELECT id,source_sha256,payload_sha256,payload FROM resources ORDER BY id'),1):
                if rid in excluded:continue
                if payload_hash(original.content(entries[rid]))!=source_sha or payload_hash(raw)!=target_sha:
                    raise ValueError('Text payload/source mismatch')
                yield rid,raw
            for rid,record in sorted(font_records.items()):
                raw=(SOURCE/'fonts'/record['file']).read_bytes()
                if payload_hash(original.content(entries[rid]))!=record['source_sha256']:raise ValueError('Font source mismatch')
                yield rid,raw
            for record,raw in map_payloads:
                rid=record['id']
                if payload_hash(original.content(entries[rid]))!=record['source_sha256']:
                    raise ValueError('Map source mismatch')
                yield rid,raw
        language_pack=OUT/'build-data/language.pack'
        language_expected=write_pack(language_pack,text_and_fonts(),text_count+len(font_records)+len(map_payloads))
    db.close()
    with ExitStack() as stack:
        original=locations(stack,[original_archive(name) for name in NAMES[1:]])
        def textures():
            for rid,record in sorted(texture_records.items()):
                reader,entry=original[rid]
                if payload_hash(reader.content(entry))!=record['source_sha256']:raise ValueError('Texture source mismatch')
                yield rid,(SOURCE/'fonts'/record['file']).read_bytes()
        surface_pack=OUT/'build-data/surface.pack'
        surface_expected=write_pack(surface_pack,textures(),len(texture_records))
    general_pack=OUT/'build-data/general.pack'
    general_expected={}
    if general_records:
        with DatReader(original_archive('client_general.dat')) as original:
            entries={e.resource_id:e for e in original.entries()}
            def general_fonts():
                for rid,record in sorted(general_records.items()):
                    if payload_hash(original.content(entries[rid]))!=record['source_sha256']:
                        raise ValueError('General font source mismatch')
                    yield rid,(SOURCE/'fonts'/record['file']).read_bytes()
            general_expected=write_pack(general_pack,general_fonts(),len(general_records))
    for name in ('DatExport.dll','msvcr71.dll','zlib1T.dll','Elanor-GPL-3.0.txt'):
        shutil.copyfile(ROOT/'client_patch/tools'/name,OUT/'tools'/name)
    compiler=Path('C:/Windows/Microsoft.NET/Framework/v4.0.30319/csc.exe')
    worker=OUT/'tools/FullDatPatchWorker.exe'
    subprocess.run([str(compiler),'/nologo','/platform:x86','/target:exe','/out:'+str(worker),str(ROOT/'native/FullDatPatchWorker.cs')],check=True)
    for name in names:
        print('Copying independent candidate:',name,flush=True)
        shutil.copyfile(original_archive(name),OUT/'work'/name)
        if file_hash(OUT/'work'/name)!=archives[name]['original_sha256']:raise ValueError('Initial candidate copy mismatch')
    groups=[('client_local_English.dat',[NAMES[0]],language_pack,language_expected),
            ('client_surface.dat',list(NAMES[1:]),surface_pack,surface_expected)]
    if general_records:groups.append(('client_general.dat',['client_general.dat'],general_pack,general_expected))
    validation={}
    for master,children,pack,expected in groups:
        write_json(OUT/'build-state.json',{'phase':'applying','group':master,'deployment_enabled':False})
        print('Applying full archive group:',master,flush=True)
        subprocess.run([str(worker),str(OUT/'work'/master),str(pack),archives[master]['original_sha256'],file_hash(pack)],
                       cwd=OUT/'tools',check=True)
        print('Independently verifying archive group:',master,flush=True)
        validation[master]=verify_group([original_archive(n) for n in children],[OUT/'work'/n for n in children],expected)
    if file_hash(SOURCE/'manifest.json')!=source_digest:raise ValueError('Source artifact manifest changed during build')
    if map_manifest and file_hash(map_manifest)!=map_digest:raise ValueError('Map manifest changed during build')
    if runtime_audit_path and file_hash(runtime_audit_path)!=runtime_digest:raise ValueError('Runtime audit changed during build')
    plan={'schema':3 if general_records else 2,'package_id':'full-draft-'+package_digest[:16],'task':'Full offline Chinese machine draft',
          'component':'DAT localization only','plugin_payloads_included':False,
          'map_manifest_sha256':map_digest,'bilingual_maps':len(map_payloads),
          'source_manifest_sha256':source_digest,'candidate_build_complete':True,'all_workspace_checks_passed':True,
          'deployment_enabled':False,'ready_for_install':False,'game_rendering_verified':False,'human_review_complete':False,
          'counts':source_manifest['counts'],'archive_validation':validation,'archives':[]}
    if runtime_audit:
        from tools.audit_window_test_source import CACHE_ID,CACHE_HASH
        with DatReader(OUT/'work/client_local_English.dat') as reader:
            entry=next(e for e in reader.entries() if e.resource_id==CACHE_ID)
            if payload_hash(reader.content(entry))!=CACHE_HASH:raise ValueError('Excluded runtime item was modified')
        plan['source_counts']=dict(plan['counts']);plan['counts']=dict(plan['counts'])
        plan['counts']['changed_resources']-=1
        plan['counts']['changed_fragments']-=3
        plan['counts']['machine_draft']-=3
        plan['counts']['preserved']+=3
        plan.update(runtime_source_audit='runtime-source-audit.json',runtime_source_audit_sha256=runtime_digest,
                    excluded_runtime_resources=[hex(CACHE_ID)],runtime_item_preserved=True)
    for name in names:
        file=OUT/'work'/name
        plan['archives'].append({'name':name,'candidate':'work/'+name,'original_sha256':archives[name]['original_sha256'],
            'original_size':archives[name]['original_size'],'patched_sha256':file_hash(file),'candidate_size':file.stat().st_size})
    shutil.copyfile(ROOT/'client_patch/full_manager.py',OUT/'manage.py')
    write_json(OUT/'install-plan.json',plan)
    write_package_docs(OUT,plan)
    write_json(OUT/'build-validation.json',{'source_artifact_files_checked':True,'archive_groups':validation,
        'source_manifest_sha256':source_digest,'candidate_files':len(names),'deployment_enabled':False,
        'game_tested':False,'elapsed_seconds':round(time.monotonic()-started,1)})
    write_json(OUT/'build-state.json',{'phase':'candidates-built','deployment_enabled':False,'install_plan':'install-plan.json'})
    print('Full candidates built and verified:',str(OUT),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--map-manifest',type=Path,help='Explicitly include the verified bilingual JPEG map manifest')
    parser.add_argument('--runtime-source-audit',type=Path,help='Explicit exact-snapshot audit; keeps one known runtime item unchanged')
    args=parser.parse_args()
    OUT=args.output.resolve()
    if not OUT.is_relative_to((ROOT/'client_patch').resolve()) or OUT==(ROOT/'client_patch').resolve():
        raise ValueError('Candidate output must be a separate directory inside client_patch/')
    try:build(args.map_manifest,args.runtime_source_audit)
    except Exception as error:
        print('Full build stopped: '+str(error),file=sys.stderr);raise
