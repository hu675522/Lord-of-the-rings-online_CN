"""Read-only SHA-256 verification of the full localization artifact format."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

FORMAT='source-bound text payload SQLite archive with standalone bitmap font resources'


def safe_file(root,name):
    relative=Path(name)
    if relative.is_absolute() or relative.drive or '..' in relative.parts:
        raise ValueError(f'清单路径不允许：{name}')
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f'清单文件缺失或越界：{name}')
    return path


def check_file(path,expected,expected_bytes=None):
    if not isinstance(expected,str) or not re.fullmatch('[0-9a-fA-F]{64}',expected):
        raise ValueError(f'无效 SHA-256：{path.name}')
    if expected_bytes is not None and path.stat().st_size!=expected_bytes:
        raise ValueError(f'文件大小不匹配：{path.name}')
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(4*1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=expected.lower():raise ValueError(f'SHA-256 不匹配：{path.name}')


def verify_manifest(path):
    path=Path(path).resolve();root=path.parent
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('format')!=FORMAT:raise ValueError('不支持的清单格式；此工具只核对全量资源素材')
    records=manifest.get('artifacts')
    if not isinstance(records,dict) or not records:raise ValueError('清单没有文件记录')
    checked=set()
    for name,record in records.items():
        file=safe_file(root,name)
        check_file(file,record['sha256'],record['bytes']);checked.add(file)
    if 'fonts/manifest.json' in records:
        font_manifest=safe_file(root,'fonts/manifest.json')
        fonts=json.loads(font_manifest.read_text(encoding='utf-8'))
        for record in fonts['records']:
            file=safe_file(font_manifest.parent,record['file'])
            check_file(file,record['sha256'],record['bytes']);checked.add(file)
    return {'ok':True,'verified_files':len(checked),'installable':False,
            'game_directory_modified':False,'note':'仅核对文件哈希；未认证发布者、兼容版本或译文质量。'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(verify_manifest(args.manifest),ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('校验失败：'+str(error),file=sys.stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
