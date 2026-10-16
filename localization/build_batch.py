"""Produce inspectable, uninstalled UI/item localization payloads offline."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lotro_zh.dat_reader import DatReader
from lotro_zh.text_resource import TextResource

BASE = ROOT / 'localization'
from localization.original_sources import original_archive
SOURCE = original_archive('client_local_English.dat')
UI_IDS = {0x250001E3, 0x25015C21, 0x25009140, 0x2502E09F, 0x250001BB,
          0x25033E37, 0x25033EC9, 0x2501D901, 0x25025E3B, 0x25014E63,
          0x25022A42, 0x25020466, 0x25033ECF}


def load(name):
    return json.loads((BASE / name).read_text(encoding='utf-8'))


def controls(text):
    """Visible wording may change; format/grammar controls may not."""
    # Links can span dynamic arguments: '<Select:IID:', id, '>', name,
    # '<\\\\Select>'. An unfinished opening tag is still executable markup.
    return re.findall(r'\{\{[^{}]*\}\}|<[^>]*>|<[A-Za-z][A-Za-z0-9_]*:[^<>]*$|^>$|\\[nqrt\[\]]|\[[^\[\]]*\]|#-?\d+:|[{}|]|%[0-9.]*[sdf]', text)


def validate_pieces(before, after):
    if len(before) != len(after):
        raise ValueError('Dynamic fragment boundaries changed')
    for left, right in zip(before, after):
        if controls(left) != controls(right):
            raise ValueError('Markup/control sequence changed: ' + repr(left))
        if len(right.encode('utf-16-le')) // 2 > 32767:
            raise ValueError('UTF-16 length limit exceeded')
    if any(re.search(r'<[A-Za-z][A-Za-z0-9_]*:[^<>]*$', p) for p in before):
        for left, right in zip(before, after):
            if re.findall(r'[<>\[\]]', left) != re.findall(r'[<>\[\]]', right):
                raise ValueError('Split-link delimiters changed')


def command_fragment(resource_id, pieces):
    """The command table stores aliases and arguments WITHOUT a leading slash."""
    return (resource_id == 0x250001ab and len(pieces) == 1 and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*(?:\s*,\s*[A-Za-z0-9][A-Za-z0-9_-]*)*', pieces[0]) is not None)


def validate_fragment(resource_id, before, after):
    validate_pieces(before, after)
    if command_fragment(resource_id, before) and before != after:
        raise ValueError('Executable command aliases/arguments changed')


def ui_translation(text, terms):
    if text in terms:
        return terms[text]
    if text.strip() in terms:
        return terms[text.strip()]
    rank_suffix = "\\nYou've earned "
    if text.endswith(rank_suffix):
        base = text[:-len(rank_suffix)].rstrip()
        if base in terms:
            return terms[base] + "\\n你已获得 "
    aliases = {'Trait Tree':'特性树','Legendary Item':'传奇物品','Reputation':'声望',
               'Destiny Point Perks':'命运点数增益', 'Group Stage':'组队阶段', 'War':'战争'}
    m = re.fullmatch(r'Open the (.+) panel\s*', text)
    if m and (m[1] in terms or m[1] in aliases):
        return '打开' + aliases.get(m[1],terms.get(m[1])) + '面板'
    m = re.fullmatch(r'Open Bag ([1-6])',text)
    if m: return '打开背包' + m[1]
    m = re.fullmatch(r'Bag ([1-6])',text)
    if m: return '背包' + m[1]
    m = re.fullmatch(r'Open the Crafting panel to the (first|second|third) Profession',text)
    if m: return '打开制造面板的第' + {'first':'一','second':'二','third':'三'}[m[1]] + '个职业'
    toggles = {'Toggle the Instance Finder panel':'切换副本查找器面板',
               'Toggle the LOTRO Store':'切换LOTRO商城', 'Toggle MyLOTRO':'切换MyLOTRO',
               'Toggle the Instance Finder Specific tab':'切换副本查找器的指定副本页签',
               'Toggle the Instance Finder Advanced tab':'切换副本查找器的高级页签',
               'Toggle the Instance Finder Simple tab':'切换副本查找器的简易页签'}
    return toggles.get(text)


def item_translation(text, terms):
    marker = re.search(r'(\[[A-Za-z]+\])$',text)
    suffix = marker[1] if marker else ''
    name = text[:marker.start()] if marker else text
    m = re.fullmatch(r'(.*?)Essences? of (.+)',name)
    if m and m[1] in terms['essence_prefixes'] and m[2] in terms['stats']:
        return terms['essence_prefixes'][m[1]] + terms['stats'][m[2]] + '精华' + suffix
    for remedy, chinese in terms['remedies'].items():
        for form in (remedy,remedy+'s',remedy.replace('Salve of ','Salves of ')):
            if name.endswith(form):
                prefix = name[:-len(form)]
                if prefix in terms['qualities']:
                    return terms['qualities'][prefix] + chinese + suffix
    if not marker:
        return None
    patterns = [(r'Chunk of (.+) Ore','矿石'),(r'Chunks of (.+) Ore','矿石'),(r'Pieces of (.+) Ore','矿石'),
                (r'(.+) Ore','矿石'),(r'(.+) Ingot','锭'),(r'(.+) Ingots','锭'),
                (r'Log of (.+) Wood','原木'),(r'Logs of (.+) Wood','原木'),
                (r'Plank of (.+) Wood','木板'),(r'Planks of (.+) Wood','木板'),
                (r'(.+) Hide','兽皮'),(r'(.+) Hides','兽皮')]
    for pattern, chinese in patterns:
        match = re.fullmatch(pattern,name)
        if match and match[1] in terms['materials']:
            return terms['materials'][match[1]] + chinese + suffix
    m = re.fullmatch(r'(Brushed |Glazed |Finished |Aged |)(.+) Leathers?',name)
    if m and m[2] in terms['materials']:
        prefixes={'':'','Brushed ':'刷制','Glazed ':'上光','Finished ':'精加工','Aged ':'陈化'}
        return prefixes[m[1]] + terms['materials'][m[2]] + '皮革' + suffix
    return None


def item_description(text, terms):
    if text in terms.get('descriptions',{}):return terms['descriptions'][text]
    obsolete='This item is obsolete.\\n\\n'
    if text.startswith(obsolete):
        rest=item_description(text[len(obsolete):],terms)
        if rest:return '此物品已停用。\\n\\n'+rest
    materials={k.casefold():v for k,v in terms['materials'].items()}
    regions={k.strip().casefold():v for k,v in terms['qualities'].items() if k}
    regions.update({'madáshi':'马达希','umbari':'昂巴'})
    m=re.fullmatch(r'This (potent|pure|infused|refined|simple|distilled|lesser|greater) (essence|salve) recovers your (morale|power) when used\.',text)
    if m:
        quality=terms['qualities'].get(m[1].capitalize()+' ')
        if quality:return '使用此'+quality+{'essence':'精华','salve':'药膏'}[m[2]]+'可恢复'+{'morale':'士气','power':'能量'}[m[3]]+'。'
    m=re.fullmatch(r'A quantity of (brushed|glazed|finished) (.+) leather, suitable for use in arms and armour\.',text)
    if m and m[2].casefold() in materials:
        return '一些'+{'brushed':'刷制','glazed':'上光','finished':'精加工'}[m[1]]+materials[m[2].casefold()]+'皮革，适合制作武器和护甲。'
    m=re.fullmatch(r'A piece of (brushed|glazed) (.+) leather(?:\.\\n\\nThis item can be used by |, used by )(.+) Tailors\.',text)
    if m and m[2].casefold() in materials and m[3].casefold() in regions:
        br='。\\n\\n' if '\\n' in text else '，'
        return '一块'+{'brushed':'刷制','glazed':'上光'}[m[1]]+materials[m[2].casefold()]+'皮革'+br+'可供'+regions[m[3].casefold()]+'裁缝使用。'
    m=re.fullmatch(r'A high-quality piece of finished (.+) leather, used by experienced (.+) Tailors\.',text)
    if m and m[1].casefold() in materials and m[2].casefold() in regions:
        return '一块高品质精加工'+materials[m[1].casefold()]+'皮革，可供熟练的'+regions[m[2].casefold()]+'裁缝使用。'
    m=re.fullmatch(r'Techniques from (.+) Foresters yield hides uniquely suited for their style of armour\.\\n\\nThis can be turned into leather by an? (.+) Forester\.',text)
    if m and m[1].casefold() in regions and m[2].casefold() in regions:
        return regions[m[1].casefold()]+'林业师处理的兽皮，特别适合其当地风格的护甲。\\n\\n'+regions[m[2].casefold()]+'林业师可将其加工为皮革。'
    m=re.fullmatch(r'An? (?:acceptable )?(.+) [Ii]ngot\.? ?(?:\\n\\nThis item can be used by |, used by )(.+) Jewellers, Metalsmiths(?:,)? and Weaponsmiths\.',text)
    if m and m[1].casefold() in materials and m[2].casefold() in regions:
        br='。\\n\\n' if '\\n' in text else '，'
        return '一块'+materials[m[1].casefold()]+'锭'+br+'可供'+regions[m[2].casefold()]+'珠宝匠、金属匠和武器匠使用。'
    m=re.fullmatch(r'A fallen (.+) branch\. This can be turned into treated wood by an? (.+) Forester\.',text)
    if m and m[1].casefold() in materials and m[2].casefold() in regions:
        return '一根掉落的'+materials[m[1].casefold()]+'树枝，'+regions[m[2].casefold()]+'林业师可将其加工为处理过的木材。'
    m=re.fullmatch(r'A large, fully-intact hide coming from a beast (?:found in the (.+) Region|in the (.+) region)\. This can be turned into leather by an? (.+) Forester\.',text)
    if m and (m[1] or m[2]).casefold() in regions and m[3].casefold() in regions:
        return '来自'+regions[(m[1] or m[2]).casefold()]+'野兽的一张完整大兽皮，'+regions[m[3].casefold()]+'林业师可将其加工为皮革。'
    m=re.fullmatch(r'Freshly-cut (.+) wood\.',text)
    if m and m[1].casefold() in materials:return '刚砍伐的'+materials[m[1].casefold()].removesuffix('木')+'木材。'
    exact = {
        'This potent essence recovers your morale when used.':'使用此强力精华可恢复士气。',
        'This potent salve recovers your power when used.':'使用此强力药膏可恢复能量。'
    }
    if text in exact:return exact[text]
    m=re.fullmatch(r'Draught cures (wounds|poisons|diseases|fear symptoms) of lesser or equal strength\. Draughts can only be used on yourself\.',text)
    effects={'wounds':'伤口','poisons':'中毒','diseases':'疾病','fear symptoms':'恐惧效果'}
    if m:return '消除强度不高于此药剂的'+effects[m[1]]+'。药剂仅可对自己使用。'
    m=re.fullmatch(r'Cures (wounds|poisons|diseases|fear symptoms) of lesser or equal strength\. Salves can be used on yourself or an ally\.',text)
    if m:return '消除强度不高于此药膏的'+effects[m[1]]+'。药膏可对自己或盟友使用。'
    m=re.fullmatch(r'The Flame of Ancalamír will turn this into ([123]) Malleable Mithrin Essences?, which can be used to craft more powerful essences\.',text)
    if m:return '安卡拉米尔之焰可将其转化为'+m[1]+'份可塑米斯林精华，用于制造更强大的精华。'
    return None


def preserve_reason(pieces):
    text=''.join(pieces).strip()
    if text.startswith('DNT') or text in {'Placeholder','ItemName','ItemInfo','PE','IM','Aa','II','III'}:
        return 'Internal/debug identifier; retained unchanged'
    if text in {'Alt','Shift','Ctrl','MyLOTRO','The Lord of the Rings Online','The Lord of the Rings Online™','<AFK>'}:
        return 'Keyboard key, product name or status marker; retained unchanged'
    if text.startswith('©'):
        return 'Copyright notice; retained unchanged'
    if any('&custom' in p or '?charname=' in p for p in pieces):
        return 'Program URL template; must not translate parameter names'
    return None


def build():
    terms, dynamic, items = load('ui-terms.json'),load('ui-dynamic.json'),load('item-terms.json')
    items['descriptions']=load('item-descriptions.json')
    terms.update(load('ui-common.json'))
    terms.update(load('ui-more-pieces.json'))
    terms.update(load('ui-housing.json'))
    overrides=load('ui-final-overrides.json')
    used_overrides=set()
    db = sqlite3.connect(BASE/'catalog.sqlite3')
    resources = {rid:(sha,title,count) for rid,sha,title,count in db.execute(
        'SELECT id,sha256,title,fragment_count FROM resources')}
    wanted = set(UI_IDS)
    wanted.update(rid for rid,(_,title,count) in resources.items() if count <= 6 and item_translation(title,items))
    output=BASE/'output/batch-001'
    records_dir=output/'records'
    records_dir.mkdir(parents=True,exist_ok=True)
    changes=[]
    pending=[]
    preserved=[]
    pending_items=[]
    preserved_items=[]
    records=[]
    with DatReader(SOURCE) as reader:
        for entry in reader.entries():
            if entry.resource_id not in wanted: continue
            raw=reader.content(entry)
            if hashlib.sha256(raw).hexdigest() != resources[entry.resource_id][0]:
                raise ValueError('Baseline no longer matches the catalog')
            text=TextResource.parse(raw)
            original=copy.deepcopy(text)
            edits=[]
            for f in text.fragments:
                translated=None
                category='common_item_names'
                if entry.resource_id in UI_IDS:
                    category='ui_and_quest_columns'
                    reason=preserve_reason(f.pieces)
                    if reason:
                        preserved.append({'resource_id':f'0x{entry.resource_id:08X}', 'fragment_id':str(f.identifier),
                                          'source_pieces':f.pieces,'reason':reason})
                        continue
                    scoped=overrides.get(f'0x{entry.resource_id:08X}',{})
                    if str(f.identifier) in scoped:
                        translated=scoped[str(f.identifier)]
                        used_overrides.add((f'0x{entry.resource_id:08X}',str(f.identifier)))
                    elif entry.resource_id == 0x250001E3 and str(f.identifier) in dynamic:
                        translated=dynamic[str(f.identifier)]
                    else:
                        values=[]
                        for piece in f.pieces:
                            value=ui_translation(piece,terms)
                            if value is None:
                                value = piece if not re.search('[A-Za-z]',piece) else None
                            values.append(value)
                        if all(v is not None for v in values): translated=values
                    if translated is None and any(re.search('[A-Za-z]{2,}',v) for v in f.pieces):
                        pending.append({'resource_id':f'0x{entry.resource_id:08X}',
                                        'fragment_id':str(f.identifier),'source_pieces':f.pieces})
                elif len(f.pieces)==1 and not f.arg_refs:
                    value=item_translation(f.pieces[0],items)
                    if value is None:
                        value=item_description(f.pieces[0],items)
                        category='common_item_descriptions'
                    if value is not None: translated=[value]
                    elif re.search('[A-Za-z]{2,}',re.sub(r'\[[^\[\]]*\]','',f.pieces[0])):
                        pending_items.append({'resource_id':f'0x{entry.resource_id:08X}',
                                              'fragment_id':str(f.identifier),'source_pieces':f.pieces})
                    elif f.pieces[0].strip():
                        preserved_items.append({'resource_id':f'0x{entry.resource_id:08X}',
                                                'fragment_id':str(f.identifier),'source_pieces':f.pieces,
                                                'reason':'Punctuation/grammar-only content; retained unchanged'})
                if translated is None or translated==f.pieces: continue
                validate_pieces(f.pieces,translated)
                edits.append({'resource_id':f'0x{entry.resource_id:08X}', 'fragment_id':str(f.identifier),
                              'category':category,'source_pieces':list(f.pieces),'chinese_pieces':translated,
                              'dynamic_refs':[v.hex() for v in f.arg_refs], 'status':'draft_format_checked',
                              'game_tested':False})
                f.pieces=translated
            if not edits: continue
            payload=text.serialize()
            parsed=TextResource.parse(payload)
            if parsed.serialize()!=payload: raise ValueError('Replacement roundtrip failed')
            for before,after in zip(original.fragments,parsed.fragments):
                if (before.identifier,before.arg_refs,before.arg_strings,len(before.pieces)) != (
                        after.identifier,after.arg_refs,after.arg_strings,len(after.pieces)):
                    raise ValueError('Dynamic arguments were altered')
                validate_pieces(before.pieces,after.pieces)
            if original.unknown!=parsed.unknown or original.trailing!=parsed.trailing:
                raise ValueError('Unrecognized header/tail was altered')
            name=f'{entry.resource_id:08X}.bin'
            (records_dir/name).write_bytes(payload)
            records.append({'id':entry.resource_id,'file':'records/'+name,'bytes':len(payload),
                            'source_sha256':hashlib.sha256(raw).hexdigest(),
                            'sha256':hashlib.sha256(payload).hexdigest(),'changed_fragments':len(edits),
                            'total_fragments':len(text.fragments),'fully_translated':False})
            changes.extend(edits)
    expected_overrides={(rid,fid) for rid,group in overrides.items() for fid in group}
    if used_overrides!=expected_overrides:
        raise ValueError('Translation overrides reference missing fragments: '+str(expected_overrides-used_overrides))
    def save(name,data):
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save('manifest.json',{'schema':1,'deployment_enabled':False,'ready_for_install':False,
                         'font_expansion_required':True,'records':records})
    save('review.json',changes)
    save('remaining-ui.json',pending)
    save('preserved-ui.json',preserved)
    save('remaining-items.json',pending_items)
    save('preserved-items.json',preserved_items)
    with (output/'review.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['resource_id','fragment_id','category','source','chinese','status'])
        for change in changes:
            writer.writerow([change['resource_id'],change['fragment_id'],change['category'],
                             ' [ARG] '.join(change['source_pieces']),' [ARG] '.join(change['chinese_pieces']),change['status']])
    summary={'changed_resources':len(records),'translated_fragments':len(changes),
             'ui_fragments':sum(c['category']=='ui_and_quest_columns' for c in changes),
             'item_name_fragments':sum(c['category']=='common_item_names' for c in changes),
             'item_description_fragments':sum(c['category']=='common_item_descriptions' for c in changes),
             'pending_ui_fragments':len(pending),'deployment_enabled':False,'game_tested':False,
             'intentionally_preserved_ui_fragments':len(preserved),
             'pending_selected_item_fragments':len(pending_items),
             'coverage_note':'Partial batch: item names, not all descriptions, stats or all items. UI coverage is limited to selected resources.',
             'output':str(output)}
    save('summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__': build()
