"""Check generated font files and original glyph pixels independently."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import BASE,OUT
from lotro_zh.dat_reader import DatReader
from lotro_zh.font_resource import BitmapFont,alpha_texture
from localization.original_sources import original_archive


def verify():
    manifest=json.loads((OUT/'fonts/manifest.json').read_text(encoding='utf-8'))
    if manifest['review_sha256']!=hashlib.sha256((OUT/'review.csv').read_bytes()).hexdigest():
        raise ValueError('Font/translation revision mismatch')
    records={r['id']:r for r in manifest['records']}
    required={ord(c) for c in (OUT/'required-characters.txt').read_text(encoding='utf-8')}
    payloads={rid:(OUT/'fonts'/r['file']).read_bytes() for rid,r in records.items()}
    for rid,payload in payloads.items():
        if hashlib.sha256(payload).hexdigest()!=records[rid]['sha256']:raise ValueError('Font payload hash mismatch')
    original={}
    with ExitStack() as stack:
        for name in ('client_local_English.dat','client_general.dat','client_surface.dat','client_surface_aux_1.datx','client_surface_aux_2.datx'):
            reader=stack.enter_context(DatReader(original_archive(name)))
            for entry in reader.entries():
                if entry.resource_id in records:original[entry.resource_id]=reader.content(entry)
        if set(original)!=set(records):raise ValueError('Source font/texture missing')
    for rid,raw in original.items():
        if hashlib.sha256(raw).hexdigest()!=records[rid]['source_sha256']:raise ValueError('Source font hash mismatch')
    texture_count=0;font_count=0
    for rid,payload in payloads.items():
        if rid>>24==0x41:
            before,after=alpha_texture(original[rid]),alpha_texture(payload)
            if after.crop((0,0,*before.size)).tobytes()!=before.tobytes():raise ValueError('Original atlas pixels changed')
            texture_count+=1
        elif rid>>24==0x42:
            before,after=BitmapFont.parse(original[rid]),BitmapFont.parse(payload)
            if after.serialize()!=payload:raise ValueError('Font roundtrip mismatch')
            if (before.identifier,before.height,before.line_height,before.tail)!=(after.identifier,after.height,after.line_height,after.tail):
                raise ValueError('Font framing changed')
            mapping={g.codepoint:g for g in after.glyphs}
            if not required<=set(mapping):raise ValueError('Glyph coverage incomplete')
            if any(mapping[g.codepoint]!=g for g in before.glyphs):raise ValueError('Original glyph metrics changed')
            for tid in after.textures:
                if not tid:continue
                atlas=alpha_texture(payloads[tid])
                if any(g.x+g.width>atlas.width or g.y+g.height>atlas.height for g in after.glyphs):
                    raise ValueError('Glyph outside atlas')
            font_count+=1
    report={'font_resources_verified':font_count,'texture_resources_verified':texture_count,
            'required_characters':len(required),'original_pixels_and_metrics_preserved':True,
            'all_glyphs_inside_atlases':True,'translation_revision_matches':True,
            'game_tested':False,'deployment_enabled':False}
    (OUT/'font-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':verify()
