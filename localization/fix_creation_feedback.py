"""Apply source-bound character-creation edits; never writes game files."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localization.build_batch import validate_pieces
from localization.full_translate import connect, dumps

TOKENS = re.compile(r'(<[^>]*>|\\+.)')


def description(source, edit):
    parts = TOKENS.split(source)
    indexes = [i for i, text in enumerate(parts)
               if text.strip() and not TOKENS.fullmatch(text)]
    expected = [parts[i].strip() for i in indexes]
    if len(indexes) != 9 or [expected[i] for i in (0, 2, 4, 6)] != ['Class Difficulty:', 'Role:', 'Gameplay:', 'Lore:']:
        raise ValueError('Class description layout changed')
    targets = ['职业难度：', edit['difficulty'], '定位：', edit['role'], '玩法：',
               edit['gameplay'], '背景：', edit['lore'], edit['inspiration']]
    for index, target in zip(indexes, targets):
        text = parts[index]
        left = text[:len(text)-len(text.lstrip())]
        right = text[len(text.rstrip()):]
        parts[index] = left + target + right
    result = ''.join(parts)
    validate_pieces([source], [result])
    return result


def main():
    edits = json.loads((ROOT / 'localization/creation-corrections.json').read_text(encoding='utf-8'))
    classes = {int(rid, 16): edit for rid, edit in edits['class_descriptions'].items()}
    class_context = set(classes) | {0x25000008, 0x25000009, 0x2500000a, 0x2500001f,
                                   0x250001bd, 0x25022bdf, 0x2502617f, 0x25019563}
    source = sqlite3.connect(ROOT / 'localization/catalog.sqlite3')
    archive = sqlite3.connect(ROOT / 'localization/full/text-resources.sqlite3')
    current = {(r, f): json.loads(t) for r, f, t in archive.execute('SELECT resource_id,fragment_id,chinese_pieces FROM review')}
    jobs = connect()
    report = []
    descriptions = set()
    for rid, fid, raw in source.execute('SELECT resource_id,id,pieces FROM fragments'):
        before = json.loads(raw)
        after = list(current[(rid, fid)])
        reason = []
        if rid in classes and fid == 209557171:
            if len(before) != 1:
                raise ValueError('Unexpected description fragment boundaries')
            after = [description(before[0], classes[rid])]
            descriptions.add(rid)
            reason.append('reviewed class description')
        else:
            for i, piece in enumerate(before):
                core = piece.strip()
                target = edits['terms'].get(core)
                if rid in class_context:
                    target = edits['contextual_class_terms'].get(core, target)
                if rid == 0x250001bd:
                    target = edits['creation_ui'].get(core, target)
                # Preserve grammar selectors in the race/class string tables.
                match = re.fullmatch(r'(?:a |an )?([A-Za-z -]+)(\[[A-Za-z]+\])', core)
                if target is None and match:
                    term = edits['terms'].get(match[1])
                    if term:
                        target = term + match[2]
                if target is not None:
                    after[i] = piece[:len(piece)-len(piece.lstrip())] + target + piece[len(piece.rstrip()):]
                    reason.append('reviewed UI terminology')
        # The engine reads this literal identifier. Translating its name breaks
        # the instruction even if the surrounding braces remain in place.
        for i, piece in enumerate(before):
            atoms = re.findall(r'\{\{[A-Za-z_]+\}\}', piece)
            translated = re.findall(r'\{\{[^{}]*\}\}', after[i])
            if atoms and len(atoms) == len(translated) and atoms != translated:
                iterator = iter(atoms)
                after[i] = re.sub(r'\{\{[^{}]*\}\}', lambda _: next(iterator), after[i])
                reason.append('restore literal engine token')
        if rid == 0x25004765 and fid == 133532190:
            after = [r'\n人类虽不及精灵长寿、矮人强健或霍比特人坚韧，却以勇气和机智闻名。\n\n']
            reason.append('reviewed race description')
        if rid == 0x25004765 and fid == 250552931:
            after = ['人类虽不及精灵长寿、矮人强健或霍比特人坚韧，却以勇气和才智闻名。他们是一个强大的种族，注定将在中土世界占据主导地位；不过，他们的意志也较为薄弱，更容易受到敌人的诱惑与诡计影响。']
            reason.append('reviewed race description')
        if after != current[(rid, fid)]:
            validate_pieces(before, after)
            jobs.execute('INSERT OR REPLACE INTO overrides VALUES(?,?,?)', (rid, fid, dumps(after)))
            report.append({'resource_id': f'0x{rid:08X}', 'fragment_id': fid,
                           'source_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                           'source': before, 'previous': current[(rid, fid)], 'target': after,
                           'reason': sorted(set(reason))})
    if descriptions != set(classes):
        raise ValueError('A class description was not found')
    jobs.commit()
    jobs.close()
    source.close()
    archive.close()
    output = ROOT / 'localization/full/creation-feedback-corrections.json'
    output.write_text(json.dumps({'class_descriptions_reviewed': len(descriptions),
        'changed_fragments': len(report), 'deployment_enabled': False, 'changes': report},
        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Creation feedback corrections saved: {len(report)} fragments; {len(descriptions)} class descriptions.')


if __name__ == '__main__':
    main()
