"""Generate standalone font payloads for the local batch; no DAT writer used."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lotro_zh.dat_reader import DatReader
from lotro_zh.font_resource import BitmapFont, extend_font, alpha_texture
from localization.original_sources import original_archive, verify_sources


def build(output=None):
    output=Path(output) if output else ROOT/'localization/output/batch-001'
    if (output/'review.json').exists():
        review_path=output/'review.json'
        changes=json.loads(review_path.read_text(encoding='utf-8'))
        chars={c for change in changes for piece in change['chinese_pieces'] for c in piece if ord(c)>127}
    else:
        review_path=output/'review.csv'
        chars=set((output/'required-characters.txt').read_text(encoding='utf-8'))
    earlier=json.loads((ROOT/'client_patch/package/translation-review.json').read_text(encoding='utf-8'))
    chars.update(earlier['new_characters'])
    source_names=('client_local_English.dat','client_general.dat',
                  'client_surface.dat','client_surface_aux_1.datx','client_surface_aux_2.datx')
    verify_sources(source_names)
    folder=output/'fonts/records'
    folder.mkdir(parents=True,exist_ok=True)
    records=[]
    stats=[]
    with ExitStack() as stack:
        fonts=[]
        for source_name in source_names[:2]:
            reader=stack.enter_context(DatReader(original_archive(source_name)))
            fonts.extend((source_name,reader,e) for e in reader.entries() if e.resource_id>>24==0x42)
        wanted={tid for _,reader,e in fonts for tid in BitmapFont.parse(reader.content(e)).textures if tid}
        textures={}
        for name in ('client_surface.dat','client_surface_aux_1.datx','client_surface_aux_2.datx'):
            reader=stack.enter_context(DatReader(original_archive(name)))
            for e in reader.entries():
                if e.resource_id in wanted:
                    textures[e.resource_id]=(reader,e)
        if set(textures)!=wanted: raise ValueError('Font texture missing')
        new_textures={}
        def record(raw,original,group):
            rid=int.from_bytes(raw[:4],'little')
            path=folder/f'{rid:08X}.bin'
            path.write_bytes(raw)
            records.append({'id':rid,'file':'records/'+path.name,'group':group,'bytes':len(raw),
                            'sha256':hashlib.sha256(raw).hexdigest(),
                            'source_sha256':hashlib.sha256(original).hexdigest()})
        def get_texture(tid):
            reader,e=textures[tid]
            return reader.content(e)
        for index,(source_name,reader,e) in enumerate(fonts,1):
            raw=reader.content(e)
            f=BitmapFont.parse(raw)
            new,atlases,details=extend_font(raw,[get_texture(tid) for tid in f.textures if tid],
                                          chars,Path(r'C:\Windows\Fonts\msyh.ttc'))
            parsed=BitmapFont.parse(new)
            if not {ord(c) for c in chars}<={g.codepoint for g in parsed.glyphs}:
                raise ValueError('Glyph coverage incomplete')
            if new!=raw: record(new,raw,source_name)
            for tid,payload in atlases.items():
                if tid in new_textures and new_textures[tid]!=payload:
                    raise ValueError('Shared texture payload conflict')
                alpha_texture(payload)
                new_textures[tid]=payload
            details['id']=f'0x{e.resource_id:08X}'
            details['source_archive']=source_name
            stats.append(details)
            if index%5==0:print(f'Font payloads generated: {index}/{len(fonts)}',flush=True)
        for tid,payload in new_textures.items():
            record(payload,get_texture(tid),'client_surface.dat group')
    summary={'deployment_enabled':False,'game_tested':False,'unicode_characters':len(chars),
             'review_sha256':hashlib.sha256(review_path.read_bytes()).hexdigest(),
             'font_resources':len(fonts),'texture_resources':len(new_textures),
             'original_metrics_preserved':all(s['original_metrics_preserved'] for s in stats),
             'original_pixels_preserved':all(s['original_pixels_preserved'] for s in stats),
             'fonts':stats,'records':records}
    (output/'fonts/manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'required-characters.txt').write_text(''.join(sorted(chars)),encoding='utf-8')
    manifest_path=output/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    manifest.update(font_expansion_required=False,font_payloads_generated=True,
                    font_manifest='fonts/manifest.json',deployment_enabled=False,ready_for_install=False)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Local font payloads: {len(fonts)} fonts, {len(new_textures)} textures, {len(chars)} required characters; no game files changed.',flush=True)


if __name__=='__main__':
    build(sys.argv[1] if len(sys.argv)>1 else None)
