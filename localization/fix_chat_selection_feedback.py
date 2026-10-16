"""Source-bound chat-link and character-selection corrections; offline only."""
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

PARTIAL = re.compile(r'<[A-Za-z][A-Za-z0-9_]*:[^<>]*$')
ACCOUNT = {'Premium Account': '高级账号', 'Free Account': '免费账号', 'VIP Account': 'VIP 账号'}
CHANNEL = {'Tribe': '部族', 'Fellowship': '小队', 'Officer': '公会官员', 'Group': '队伍', 'Kinship': '公会', 'Raid': '团队'}


def chat_link(source):
    """Use the exact source protocol, translating only its visible wording."""
    target = list(source)
    for i, text in enumerate(target):
        for left, right in CHANNEL.items():
            text = text.replace('[' + left + '\\]', '[' + right + '\\]')
        text = text.replace('You tell ', '你对').replace('> tells you, ', '>对你说：')
        text = text.replace('> shouts, ', '>喊道：').replace('> says, ', '>说：')
        if source[0].startswith('You tell ') and text.endswith(">, '"):
            text = text.replace(">, '", ">说：'")
        target[i] = text
    validate_pieces(source, target)
    return target


def main():
    ui = json.loads((ROOT/'localization/character-selection-corrections.json').read_text(encoding='utf-8'))
    source = sqlite3.connect(ROOT/'localization/catalog.sqlite3')
    archive = sqlite3.connect(ROOT/'localization/full/text-resources.sqlite3')
    current = {(r,f): json.loads(t) for r,f,t in archive.execute('SELECT resource_id,fragment_id,chinese_pieces FROM review')}
    jobs = connect()
    edits = []; seen = set(); links = 0
    for rid, fid, raw in source.execute('SELECT resource_id,id,pieces FROM fragments'):
        before = json.loads(raw); after = list(current[rid,fid]); reasons = []
        if any(PARTIAL.search(p) for p in before):
            if rid == 0x250001a7:
                after = chat_link(before)
            elif rid == 0x250001b7:
                # These are executable wrappers, including English article grammar.
                after = list(before)
            else:
                raise ValueError(f'Unreviewed split link: {rid:x}/{fid}')
            reasons.append('restore exact split-link protocol'); links += 1
        if rid == 0x250001af and before == ['IID: ', '']:
            after = before; reasons.append('preserve technical identifier label')
        if rid == 0x250001a7:
            for i,p in enumerate(before):
                if p in {'LFF','LFG'}:
                    after[i] = '组队' if p == 'LFF' else '寻队'
                    reasons.append('chat channel terminology')
        if rid == 0x2501938b and len(before) == 1 and before[0] in ACCOUNT:
            after = [ACCOUNT[before[0]]]; reasons.append('account status terminology')
        if rid == 0x250001bd:
            for i,p in enumerate(before):
                if p in ui:
                    after[i] = ui[p]; seen.add(p); reasons.append('reviewed character UI wording')
            if before == ['', ' of ', ' Character Slots Used']:
                after = ['已用角色栏位 ', ' / ', '']; reasons.append('dynamic slot count layout')
            if before == ['', ' of ', ' Advanced Character ']:
                after = ['高级角色 ', ' / ', '']; reasons.append('dynamic slot count layout')
            # Keep all argument boundaries and quote/newline delimiters intact.
            specials = {
                6110948: ['此角色未达到种族变更的最低等级。所需等级：', '。'],
                47999540: ['购买资料片可额外获得 ', ' 个角色栏位。'],
                79501261: ["请输入 '", "' 到确认框，以重置此角色。"],
                122376861: ["请输入 '", "' 到确认框，以删除此角色。"],
                141126597: ['', r'\n警告：删除此角色时，其名下住宅将自动被放弃。'],
                235567602: ['你有 ', ' 个角色和 ', ' 个角色栏位。请选择要保留为可用状态的角色。'],
                249522928: ['任意角色达到 ', ' 级即可解锁怪物扮演。'],
            }
            if fid in specials:
                after = specials[fid]; reasons.append('reviewed dynamic character UI prompt')
        if reasons:
            validate_pieces(before, after)
            jobs.execute('INSERT OR REPLACE INTO overrides VALUES(?,?,?)', (rid,fid,dumps(after)))
            edits.append({'resource_id':f'0x{rid:08X}', 'fragment_id':fid,
                'source_sha256':hashlib.sha256(raw.encode()).hexdigest(), 'source':before,
                'previous':current[rid,fid], 'target':after, 'changed':after!=current[rid,fid], 'reasons':reasons})
    if seen != set(ui):
        raise ValueError('UI source snapshot mismatch: ' + repr(set(ui)-seen))
    if links != 27:
        raise ValueError('Split-link catalog snapshot changed: ' + str(links))
    jobs.commit(); jobs.close(); archive.close(); source.close()
    report = {'deployment_enabled':False, 'split_link_fragments_reviewed':links,
              'changed_fragments':sum(e['changed'] for e in edits), 'edits':edits}
    (ROOT/'localization/full/chat-selection-feedback-corrections.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Feedback corrections:',report['changed_fragments'],'changed;',links,'split links reviewed',flush=True)


if __name__ == '__main__': main()
