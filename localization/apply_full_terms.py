"""Source-guarded consistency edits. Working spellings are explicit, editable."""
import collections
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import BASE,OUT,connect,normalize_input
from localization.full_quality import flags_for,audit


def main():
    db=connect()
    terms=json.loads((BASE/'full_terms.json').read_text(encoding='utf-8'))
    compiled=[(re.compile(r'\b(?:'+row['english']+r')\b',re.I),row) for row in terms]
    changed=0;counts=collections.Counter()
    for sid,source,old in db.execute("SELECT id,source,translation FROM segments WHERE status='machine_draft'").fetchall():
        value=old;normalized=normalize_input(source)
        for pattern,row in compiled:
            if not pattern.search(normalized):continue
            before=value
            value=pattern.sub(row['chinese'],value)
            for wrong in row['wrong']:value=value.replace(wrong,row['chinese'])
            if value!=before:counts[row['chinese']]+=1
        if value!=old:
            db.execute('UPDATE segments SET translation=?,qa=? WHERE id=?',(value,','.join(flags_for(source,value)),sid));changed+=1
    db.commit()
    qa=audit(db)
    report={'changed_units':changed,'term_changes':dict(counts),'quality_flags':dict(qa),
            'spellings_are_working_glossary':True,'human_review_complete':False,'deployment_enabled':False}
    (OUT/'term-consistency.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    db.close()


if __name__=='__main__':main()
