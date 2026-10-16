"""Export a small source allowlist locally, without Git/network/deployment."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
FILES=('README.md','.gitignore','.gitattributes','requirements-dev.txt','samples.json',
       'CONTRIBUTING.md','THIRD_PARTY_NOTICES.md','CHANGELOG.md',
       'build_client_patch.py','build_full_patch.py','patch_probe.py','client_patch/README.md','client_patch/manage.py',
       'client_patch/full_manager.py',
       'client_patch/deployment-policy.json','client_patch/tools/Elanor-GPL-3.0.txt',
       'localization/README.md','localization/full_terms.json','localization/full_corrections.json',
       'localization/creation-corrections.json',
       'localization/character-selection-corrections.json',
       'localization/options-feedback-corrections.json',
       'localization/maps/glossary.json','localization/maps/compound-glossary.json',
       'localization/maps/map-overrides.json','localization/maps/extra-labels.json',
       'localization/maps/qa-additions.json','localization/maps/ocr-corrections.json',
       'localization/maps/ocr-exclusions.json')
PATTERNS=('docs/*.md','.github/*.md','.github/ISSUE_TEMPLATE/*.md','lotro_zh/*.py',
          'tests/*.py','tools/*.py','tools/cleanup_restored_map_test.ps1','native/*.cs','localization/*.py',
          'localization/ui-*.json','localization/item-*.json','client_patch/translations/*.json',
          'localization/store/*.js','localization/store/*.cjs','localization/store/*.py','localization/store/*.md','tests/*.cjs',
          'localization/item_lookup/*.py','localization/item_lookup/*.md','localization/item_lookup/plugin/*.lua','localization/item_lookup/plugin/*.plugin',
          'localization/maps/*.md','localization/maps/*.py','localization/maps/*.ps1')

PRIVATE_PREFIXES=('docs/FEEDBACK-', 'docs/TEST-DEPLOYMENT-', 'tools/record_complete_test_')
PRIVATE_FILES={'docs/LOCAL_TEST.md','docs/PLUGIN-014-LOCAL-TEST.md','localization/maps/PROGRESS.md'}


def prepare(root,output):
    root=Path(root).resolve();output=Path(output).resolve();release=(root/'release').resolve()
    if not release.is_relative_to(root) or not output.is_relative_to(release) or output==release:
        raise ValueError('源码预览目标必须是项目 release/ 下的新目录')
    if output.exists():raise FileExistsError('目标已存在，未覆盖；请指定新的预览目录')
    selected={root/name for name in FILES if (root/name).is_file()}
    for pattern in PATTERNS:selected.update(p for p in root.glob(pattern) if p.is_file())
    selected.update(p for p in root.glob('distribution/*.py') if p.is_file())
    selected={p for p in selected if p.relative_to(root).as_posix() not in PRIVATE_FILES
              and not p.relative_to(root).as_posix().startswith(PRIVATE_PREFIXES)}
    for name in ('LICENSE','LICENSE.md','LICENSE.txt'):
        if (root/name).is_file():selected.add(root/name)
    records=[]
    for file in sorted(selected):
        if file.is_symlink() or not file.resolve().is_relative_to(root):
            raise ValueError('源码白名单出现链接或越界文件：'+str(file.relative_to(root)))
        if file.stat().st_size>2*1024*1024:raise ValueError('源码白名单出现大型文件：'+str(file.relative_to(root)))
        data=file.read_bytes()
        records.append({'file':file.relative_to(root).as_posix(),'bytes':len(data),
                        'sha256':hashlib.sha256(data).hexdigest()})
    # No recursive directory copy: excluded large/private trees are never read.
    output.mkdir(parents=True,exist_ok=False)
    for record in records:
        target=output/record['file'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/record['file'],target)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('导出期间源码变化，预览不完整：'+record['file'])
    report={'kind':'source-preview','created_utc':datetime.now(timezone.utc).isoformat(),
            'file_count':len(records),'total_bytes':sum(r['bytes'] for r in records),
            'files':records,'upload_performed':False,'ready_for_public_release':False,
            'review_required':['project license and third-party distribution scope',
                               'small source examples and translation data','privacy and environment portability'],
            'contains_game_backups':False,'contains_full_translation_database':False,
            'contains_model_or_native_binaries':False,'installable':False}
    (output/'SOURCE_PREVIEW.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'release/source-preview')
    args=parser.parse_args()
    output=args.output if args.output.is_absolute() else ROOT/args.output
    try:
        report=prepare(ROOT,output)
        print(json.dumps({'output':str(output),'files':report['file_count'],
                          'bytes':report['total_bytes'],'upload_performed':False,'installable':False},ensure_ascii=False,indent=2))
    except (OSError,ValueError) as error:
        print('导出停止：'+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
