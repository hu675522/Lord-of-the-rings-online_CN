"""Resolve original archives after user-authorized backup cleanup.

The game fallback is read-only. Call verify_sources before building; text
reassembly additionally validates every source resource against its catalog.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def original_archive(name):
    backup = ROOT / 'client_patch/backups' / (name + '.original')
    if backup.exists() or not (ROOT / 'data/original-archives.json').exists():
        return backup
    config = json.loads((ROOT / 'data/original-archives.json').read_text(encoding='utf-8'))
    if name not in config['archives']:
        raise ValueError('Source archive is not registered: ' + name)
    # Once a test version is installed, the live game is no longer an English
    # source. Keep subsequent builds bound to that deployment's verified backup.
    if config.get('source_backup_directory'):
        return Path(config['source_backup_directory']) / (name + '.original')
    return Path(config['game_directory']) / name


def verify_sources(names):
    config = json.loads((ROOT / 'data/original-archives.json').read_text(encoding='utf-8'))
    for name in names:
        path = original_archive(name)
        info = config['archives'][name]
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size != info['bytes'] or digest != info['sha256']:
            raise ValueError('Original resource version changed: ' + name)
        print('Read-only source verified: ' + name, flush=True)
