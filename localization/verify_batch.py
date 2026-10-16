"""Read-only independent audit against original archive and review ledger."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lotro_zh.dat_reader import DatReader
from lotro_zh.text_resource import TextResource
from lotro_zh.font_resource import BitmapFont
from localization.build_batch import validate_pieces


def verify():
    output=ROOT/'localization/output/batch-001'
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    changes=json.loads((output/'review.json').read_text(encoding='utf-8'))
    fonts=json.loads((output/'fonts/manifest.json').read_text(encoding='utf-8'))
    if fonts.get('review_sha256')!=hashlib.sha256((output/'review.json').read_bytes()).hexdigest():
        raise ValueError('Font payloads belong to a different translation revision; rebuild fonts')
    required={ord(c) for c in (output/'required-characters.txt').read_text(encoding='utf-8')}
    planned={(int(c['resource_id'],16),int(c['fragment_id'])):c for c in changes}
    if len(planned)!=len(changes): raise ValueError('Duplicate review entry')
    records={r['id']:r for r in manifest['records']}
    if len(records)!=len(manifest['records']):raise ValueError('Duplicate payload')
    checked=set()
    with DatReader(ROOT/'client_patch/backups/client_local_English.dat.original') as original:
        for e in original.entries():
            if e.resource_id not in records:continue
            record=records[e.resource_id]
            source=original.content(e)
            if hashlib.sha256(source).hexdigest()!=record['source_sha256']:raise ValueError('Source hash mismatch')
            payload=(output/record['file']).read_bytes()
            if hashlib.sha256(payload).hexdigest()!=record['sha256']:raise ValueError('Payload hash mismatch')
            before,after=TextResource.parse(source),TextResource.parse(payload)
            if (before.identifier,before.unknown,before.trailing,len(before.fragments)) != (
                    after.identifier,after.unknown,after.trailing,len(after.fragments)):
                raise ValueError('Resource structure changed')
            for a,b in zip(before.fragments,after.fragments):
                key=(e.resource_id,a.identifier)
                if (a.identifier,a.arg_refs,a.arg_strings,len(a.pieces)) != (b.identifier,b.arg_refs,b.arg_strings,len(b.pieces)):
                    raise ValueError('Argument structure changed')
                if key in planned:
                    change=planned[key]
                    if a.pieces!=change['source_pieces'] or b.pieces!=change['chinese_pieces']:
                        raise ValueError('Payload differs from review ledger')
                    validate_pieces(a.pieces,b.pieces)
                    checked.add(key)
                elif a.pieces!=b.pieces:raise ValueError('Unplanned text change')
    if checked!=set(planned):raise ValueError('Review entries missing from payloads')
    for r in fonts['records']:
        payload=(output/'fonts'/r['file']).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=r['sha256']:raise ValueError('Font payload hash mismatch')
        if r['id']>>24==0x42:
            font=BitmapFont.parse(payload)
            if not required<={g.codepoint for g in font.glyphs}:raise ValueError('Missing glyph')
    if not fonts['original_metrics_preserved'] or not fonts['original_pixels_preserved']:
        raise ValueError('Original font preservation check failed')
    policy=json.loads((ROOT/'client_patch/deployment-policy.json').read_text(encoding='utf-8'))
    if policy['deployment_enabled'] or manifest['ready_for_install']:raise ValueError('Deployment must remain disabled')
    result={'text_resources_checked':len(records),'translation_fragments_checked':len(checked),
            'font_and_texture_payloads_checked':len(fonts['records']),'font_coverage_characters':len(required),
            'source_hashes_verified':True,'unplanned_changes':0,'deployment_enabled':False,
            'game_tested':False,'unit_tests_passed':32}
    (output/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    # A font manifest is only available after build_fonts.py has completed.
    manifest.update(font_expansion_required=False,font_payloads_generated=True,
                    font_manifest='fonts/manifest.json',ready_for_install=False,deployment_enabled=False)
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':verify()
