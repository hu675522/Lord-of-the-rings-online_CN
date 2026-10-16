"""Verify executable command literals and reviewed UI in the rebuilt payload."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localization.build_batch import command_fragment
from localization.fix_commands_options_feedback import UI_SCOPES


def main():
    folder = ROOT / 'localization/full'
    db = sqlite3.connect((folder / 'text-resources.sqlite3').as_uri() + '?mode=ro', uri=True)
    terms = json.loads((ROOT / 'localization/options-feedback-corrections.json').read_text(encoding='utf-8'))
    scopes = UI_SCOPES
    tokens = set(); checked = 0; ui = []
    ids=(*scopes,0x250001ab)
    for rid, fid, left, right in db.execute('SELECT resource_id,fragment_id,source_pieces,chinese_pieces FROM review WHERE resource_id IN ('+','.join('?' for _ in ids)+')',ids):
        source, target = json.loads(left), json.loads(right)
        if command_fragment(rid, source):
            if source != target: raise ValueError('Command literal changed')
            tokens.add(source[0]); checked += 1
        elif rid in scopes:
            for a, b in zip(source, target):
                if a in terms[scopes[rid]]:
                    if b != terms[scopes[rid]][a]: raise ValueError('UI correction missing: ' + a)
                    ui.append({'resource_id': hex(rid), 'fragment_id': fid, 'source': a, 'target': b})
    if checked != 238 or not {'plugins', 'load', 'unload', 'refresh'} <= tokens:
        raise ValueError('Expected command table missing')
    if not {'Scenery', 'IMs', 'LFF', 'Very High'} <= {r['source'] for r in ui}:
        raise ValueError('Screenshot labels missing')
    if sum(r['source']=='LFF' and r['resource_id']=='0x25012805' for r in ui)!=3:
        raise ValueError('Chat dropdown LFF labels missing')
    report = {'protected_command_fragments': checked, 'reviewed_ui_occurrences': len(ui),
              'payload_sha256': hashlib.sha256((folder / 'text-resources.sqlite3').read_bytes()).hexdigest(),
              'ui': ui, 'game_tested': False, 'deployment_enabled': False}
    (folder / 'commands-options-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(checked, 'command fragments and', len(ui), 'UI occurrences verified')


if __name__ == '__main__': main()
