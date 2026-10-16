"""Round-trip the map resources in one disposable workspace DAT, never deploy."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build_full_patch import write_pack,verify_group,file_hash
from localization.original_sources import original_archive
from localization.maps.verify_maps import load_payloads


def main():
    root=(ROOT/'artifacts/map-dat-validation').resolve()
    if not root.is_relative_to(ROOT/'artifacts'):raise ValueError('Workspace validation path escaped')
    work=root/'work';binary=root/'tools';work.mkdir(parents=True,exist_ok=True);binary.mkdir(exist_ok=True)
    target=(work/'client_local_English.dat').resolve()
    if not target.is_relative_to(work.resolve()):raise ValueError('Candidate escaped validation workspace')
    if target.exists():raise ValueError('Existing candidate preserved; inspect before another round-trip')
    manifest=ROOT/'localization/maps/bilingual-draft/manifest.json';digest=file_hash(manifest)
    _,payloads=load_payloads(manifest,218)
    pack=root/'maps.pack';expected=write_pack(pack,((r['id'],raw) for r,raw in payloads),218)
    source=original_archive('client_local_English.dat');original_digest=file_hash(source)
    config=json.loads((ROOT/'data/original-archives.json').read_text(encoding='utf8'))
    if config['archives']['client_local_English.dat']['sha256']!=original_digest:raise ValueError('Original DAT hash mismatch')
    for name in ('DatExport.dll','msvcr71.dll','zlib1T.dll'):shutil.copyfile(ROOT/'client_patch/tools'/name,binary/name)
    worker=binary/'FullDatPatchWorker.exe'
    subprocess.run([r'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe','/nologo','/platform:x86',
        '/target:exe','/out:'+str(worker),str(ROOT/'native/FullDatPatchWorker.cs')],check=True)
    print('Copying one disposable English DAT into the workspace',flush=True)
    try:
        shutil.copyfile(source,target)
        subprocess.run([str(worker),str(target),str(pack),original_digest,file_hash(pack)],cwd=binary,check=True)
        result=verify_group([source],[target],expected)
        if file_hash(manifest)!=digest:raise ValueError('Map assets changed during archive verification')
        result.update(maps=218,map_manifest_sha256=digest,source_dat_sha256=original_digest,
            candidate_dat_sha256=file_hash(target),game_tested=False,deployed=False)
        (root/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    finally:
        # Exact known temporary files only; no directory recursion or game writes.
        if target.exists():target.unlink()
        if pack.exists():pack.unlink()
        print('Disposable workspace DAT and payload pack removed',flush=True)


if __name__=='__main__':main()
