"""SHA-bound fixed-block differences; no native dependency on the player PC."""
import hashlib
import json
import math
from pathlib import Path
import zipfile

BLOCK = 65536


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(source, candidate, target):
    source, candidate, target = map(Path, (source, candidate, target))
    meta = {'schema': 1, 'block_size': BLOCK, 'original_size': source.stat().st_size,
            'candidate_size': candidate.stat().st_size, 'original_sha256': digest(source),
            'patched_sha256': digest(candidate), 'blocks': []}
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as left, candidate.open('rb') as right, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for index in range(math.ceil(meta['candidate_size'] / BLOCK)):
            raw = right.read(BLOCK)
            if left.read(BLOCK) != raw:
                meta['blocks'].append({'index': index, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
                out.writestr(f'blocks/{index}.bin', raw)
        out.writestr('delta.json', json.dumps(meta, separators=(',', ':')))
    return meta


def inspect(archive):
    meta = json.loads(archive.read('delta.json'))
    if meta['schema'] != 1 or meta['block_size'] != BLOCK:
        raise ValueError('Unsupported difference format')
    size = meta['candidate_size']
    if not isinstance(size, int) or size <= 0 or meta['original_size'] <= 0:
        raise ValueError('Invalid resource size')
    seen = set()
    for row in meta['blocks']:
        index = row['index']
        if not isinstance(index, int) or index < 0 or index >= math.ceil(size / BLOCK) or index in seen:
            raise ValueError('Duplicate/out-of-range difference block')
        seen.add(index)
        if row['bytes'] != min(BLOCK, size - index * BLOCK):
            raise ValueError('Incorrect difference block size')
    names = ['delta.json'] + [f'blocks/{i}.bin' for i in seen]
    if len(archive.namelist()) != len(names) or set(archive.namelist()) != set(names):
        raise ValueError('Unexpected/duplicate difference entries')
    return meta


def apply(source, delta, target, expected):
    source, delta, target = map(Path, (source, delta, target))
    if target.exists():
        raise ValueError('Candidate target already exists')
    temp = target.with_name(target.name + '.building')
    if temp.exists():
        raise ValueError('Incomplete candidate found; preserve it for inspection')
    with zipfile.ZipFile(delta) as archive:
        meta = inspect(archive)
        for key in ('original_size', 'candidate_size', 'original_sha256', 'patched_sha256'):
            if meta[key] != expected[key]:
                raise ValueError('Difference manifest mismatch: ' + key)
        if source.stat().st_size != meta['original_size'] or digest(source) != meta['original_sha256']:
            raise ValueError('English source version mismatch')
        changed = {r['index']: r for r in meta['blocks']}
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source.open('rb') as original, temp.open('xb') as out:
                for index in range(math.ceil(meta['candidate_size'] / BLOCK)):
                    count = min(BLOCK, meta['candidate_size'] - index * BLOCK)
                    if index in changed:
                        row = changed[index]
                        info = archive.getinfo(f'blocks/{index}.bin')
                        if info.file_size != count:
                            raise ValueError('Invalid block entry size')
                        raw = archive.read(info)
                        if hashlib.sha256(raw).hexdigest() != row['sha256']:
                            raise ValueError('Difference block checksum mismatch')
                    else:
                        original.seek(index * BLOCK)
                        raw = original.read(count)
                    if len(raw) != count:
                        raise ValueError('Missing/truncated difference block')
                    out.write(raw)
            if digest(temp) != meta['patched_sha256']:
                raise ValueError('Reconstructed candidate checksum mismatch')
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
