"""Explicit paragraph edits retaining unusual double-escaped source controls."""
from pathlib import Path
import json
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import BASE,OUT,connect,dumps
from localization.build_batch import validate_pieces

corrections=[
 (0x2503df91,162883761,[
  '阿玛妈妈（Mother Amma）建议趁这次旅程好好看看铁谷（Ironfold），因为宝石匠们不常去那里。她列出了一份沿途可做之事的清单。 '+r'\\q'+'宝石匠总会设法为遇到的人带来好处！'+r'\\q'+'她这么说，我确实无法反驳。所以，她的清单上既有一些能保护这片土地和居民安全的任务，也有几位我久未谋面的铁谷世交。我对先做哪件事没有特别偏好，因此就把决定权交给你， ',
  '。不如挑四件左右，沿着前往雅恩法斯特（Járnfast）的路去完成？']),
 (0x25007e89,250619685,[
  '<u>斧与火</u>'+r'\n\q'+'艾辛格的乌鲁克人前来夺取南库鲁尼尔（Nan Curunir）仅存的树木——树人快枝（Quickbeam）的林地。'+r'\\n\\n'+'若这些黑暗爪牙发现树人就在离艾辛格如此之近的地方，萨鲁曼必会在其大军出征洛汗骑兵之前，将烽火烧向范贡（Fangorn）。'+r'\q']),
 (0x2500209c,162970849,['你们两个去找这个'+r'\\q'+'巴金斯（Baggins）。'+r'\\q'])
]

def main():
    db=connect();catalog=sqlite3.connect(BASE/'catalog.sqlite3')
    report=[]
    for rid,fid,target in corrections:
        source=json.loads(catalog.execute('SELECT pieces FROM fragments WHERE resource_id=? AND id=?',(rid,fid)).fetchone()[0])
        validate_pieces(source,target)
        db.execute('INSERT OR REPLACE INTO overrides VALUES(?,?,?)',(rid,fid,dumps(target)))
        report.append({'resource_id':f'0x{rid:08X}','fragment_id':fid,'source':source,'target':target})
    for fid in (162883715,162883718):
        rid=0x250554d3
        row=db.execute('SELECT pieces FROM overrides WHERE resource_id=? AND fragment_id=?',(rid,fid)).fetchone()
        if not row:raise ValueError('Legacy quest override missing')
        target=json.loads(row[0])
        if not any(r'\q' in p for p in target):
            target=[p.replace('埃马克斯杜尔（Emax Dûl）',r'\q埃马克斯杜尔（Emax Dûl）\q') for p in target]
        source=json.loads(catalog.execute('SELECT pieces FROM fragments WHERE resource_id=? AND id=?',(rid,fid)).fetchone()[0])
        validate_pieces(source,target)
        db.execute('UPDATE overrides SET pieces=? WHERE resource_id=? AND fragment_id=?',(dumps(target),rid,fid))
        report.append({'resource_id':f'0x{rid:08X}','fragment_id':fid,'source':source,'target':target})
    db.commit();db.close();catalog.close()
    (OUT/'context-corrections.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Context corrections applied:',len(report),flush=True)


if __name__=='__main__':main()
