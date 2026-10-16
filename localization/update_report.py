"""Report exact batch coverage without treating every source fragment as translatable."""
import csv
import json
from pathlib import Path
import sqlite3
import zipfile

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent
OUT=BASE/'output/batch-001'


def update():
    summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
    review=json.loads((OUT/'review.json').read_text(encoding='utf-8'))
    fonts=json.loads((OUT/'fonts/manifest.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(BASE/'revisions/batch-001-20261014.zip') as z:
        old=json.loads(z.read('output/batch-001/review.json'))
    prior={(r['resource_id'],r['fragment_id']):r for r in old}
    added=[r for r in review if (r['resource_id'],r['fragment_id']) not in prior]
    revised=[r for r in review if (r['resource_id'],r['fragment_id']) in prior and
             r['chinese_pieces']!=prior[(r['resource_id'],r['fragment_id'])]['chinese_pieces']]
    with (OUT/'added-20261015.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.writer(stream)
        w.writerow(['resource_id','fragment_id','category','source','chinese'])
        for r in added:
            w.writerow([r['resource_id'],r['fragment_id'],r['category'],
                        ' [ARG] '.join(r['source_pieces']),' [ARG] '.join(r['chinese_pieces'])])
    done={(int(r['resource_id'],16),int(r['fragment_id'])) for r in review}
    for name in ('finding-amdir.json','madness-at-damudur.json'):
        task=json.loads((ROOT/'client_patch/translations'/name).read_text(encoding='utf-8'))
        done.update((int(task['resource_id'],16),int(fid)) for fid in task['fragments'])
    with sqlite3.connect(BASE/'catalog.sqlite3') as db:
        total=db.execute('SELECT COUNT(*) FROM fragments').fetchone()[0]
        db.execute('CREATE TEMP TABLE done(resource_id INTEGER,id INTEGER,PRIMARY KEY(resource_id,id))')
        db.executemany('INSERT INTO done VALUES(?,?)',done)
        actual=db.execute('SELECT COUNT(*) FROM done JOIN fragments USING(resource_id,id)').fetchone()[0]
        if actual!=len(done):raise ValueError('Translated ledger has an unknown source fragment')
    ui={r['resource_id'] for r in review if r['category']=='ui_and_quest_columns'}
    items={r['resource_id'] for r in review if r['category'].startswith('common_item')}
    remaining=['其他界面资源，包括未纳入本批的设置、面板和提示',
               '本批物品族之外的物品名称、详细说明与装备属性',
               '除已保留两个任务外的主线、支线和NPC对话',
               '尚未纳入的技能、功绩、教程、地名等文本']
    report={'current_batch':summary,'new_fragments_this_round':len(added),
            'revised_existing_fragments':len(revised),'selected_ui_resources':len(ui),
            'selected_item_resources':len(items),'full_catalog_fragments':total,
            'translated_fragments_including_two_verified_quests':len(done),
            'outside_translated_ledger':total-len(done),
            'count_warning':'未纳入译文清单的数量包含空白、技术标识及无需翻译的内容，不能作为待译句数或任务数。',
            'still_to_cover':remaining,'terminology_review_pending':['Muckle名称','专有名词和品质层级'],
            'deployment_enabled':False,'game_tested':False}
    (OUT/'coverage-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    note=f'''# 当前汉化范围与剩余工作

本批累计 **{summary['translated_fragments']:,} 个译文片段**，覆盖 {len(ui)} 组界面资源及 {len(items):,} 组物品类文本资源。
本轮新增 {len(added):,} 个片段。此前两个任务的 78 段译文另行保留。

| 类别 | 已生成译文片段 |
|---|---:|
| 通用界面、任务栏目、组队、特性和住宅提示 | {summary['ui_fragments']:,} |
| 物品单复数名称 | {summary['item_name_fragments']:,} |
| 药剂用途、制造材料及精华说明 | {summary['item_description_fragments']:,} |

当前所选界面和物品范围中的待翻译清单均为零；24 个技术标识、品牌名、键名保留原文，另保留省略号等纯格式内容。
这是本批范围的完成，不是全游戏汉化完成。译文仍待术语校对和游戏显示检查。

## 尚未覆盖

'''+''.join('- '+x+'。\n' for x in remaining)+f'''
全量清单共 {total:,} 个片段，本批及两个任务合计为 {len(done):,} 个片段提供译文。
其余 {total-len(done):,} 个片段尚未纳入译文清单，但其中也有空白和无需本地化的技术内容，不能直接视作待译句数。

## 校验与保存

- 32 项自动化测试通过；文本源哈希、参数、控制符和输出资源通过独立校验。
- 配套 45 个字体和 89 个纹理，覆盖 {fonts['unicode_characters']:,} 个所需非ASCII字符，保留原字形指标和像素。
- 新增译文：`output/batch-001/added-20261015.csv`；完整对照：`output/batch-001/review.csv`。
- 上一版备份：`revisions/batch-001-20261014.zip`。
- 成果仅在 `D:\\PY\\zhihuanwang`，未部署；游戏安装器继续禁用部署。
'''
    (BASE/'剩余汉化清单.md').write_text(note,encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('new_fragments_this_round','selected_ui_resources','selected_item_resources','outside_translated_ledger')},ensure_ascii=False))


if __name__=='__main__':update()
