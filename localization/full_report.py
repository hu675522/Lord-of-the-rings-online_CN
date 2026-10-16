"""Publish local-only coverage, provenance and limitations after validation."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from localization.full_translate import BASE,OUT
from localization.build_batch import SOURCE


def main():
    summary=json.loads((OUT/'build-summary.json').read_text(encoding='utf-8'))
    validation=json.loads((OUT/'validation.json').read_text(encoding='utf-8'))
    fonts=json.loads((OUT/'fonts/manifest.json').read_text(encoding='utf-8'))
    db=sqlite3.connect(OUT/'jobs.sqlite3')
    statuses=dict(db.execute('SELECT status,count(*) FROM segments GROUP BY status'))
    active=set()
    for raw, in db.execute('SELECT template FROM pieces'):
        active.update(atom['segment'] for atom in json.loads(raw) if 'segment' in atom)
    source_plan={'fragments':summary['counts']['fragments'],
        'unique_pieces':db.execute('SELECT count(*) FROM pieces').fetchone()[0],
        'all_prepared_units':sum(statuses.values()),'referenced_units':len(active),
        'obsolete_units_retained_for_audit':sum(statuses.values())-len(active),
        'context_overrides':db.execute('SELECT count(*) FROM overrides').fetchone()[0],
        'translation_unit_statuses':statuses,'pending_units':statuses.get('pending',0),'error_units':statuses.get('error',0)}
    (OUT/'source-plan.json').write_text(json.dumps(source_plan,indent=2),encoding='utf-8')
    qa_counts=collections.Counter()
    with (OUT/'quality-segments.jsonl').open('w',encoding='utf-8') as file:
        for sid,s,t,status,qa in db.execute("SELECT * FROM segments WHERE qa!=''"):
            qa_counts.update(qa.split(','))
            file.write(json.dumps({'id':sid,'source':s,'chinese':t,'status':status,'qa':qa},ensure_ascii=False)+'\n')
    db.close()
    font_validation=json.loads((OUT/'font-validation.json').read_text(encoding='utf-8'))
    test_log=(OUT/'tests.log').read_text(encoding='utf-8')
    test_count=re.search(r'Ran (\d+) tests',test_log)
    if not test_count or test_log.strip().splitlines()[-1]!='OK':raise ValueError('Current test suite did not pass')
    artifacts=['text-resources.sqlite3','review.csv','required-characters.txt','validation.json','font-validation.json','fonts/manifest.json','tests.log']
    artifacts.extend(name for name in ('creation-feedback-corrections.json','chat-selection-feedback-corrections.json','commands-options-feedback-corrections.json','commands-options-validation.json','font-reuse-validation.json','general-candidate-validation.json') if (OUT/name).exists())
    manifest={'format':'source-bound text payload SQLite archive with standalone bitmap font resources',
        'source':str(SOURCE),
        'counts':summary['counts'],'translation_unit_statuses':statuses,'quality_flags':dict(qa_counts),
        'font_resources':fonts['font_resources'],'texture_resources':fonts['texture_resources'],
        'unicode_characters':fonts['unicode_characters'],'human_review_complete':False,'game_tested':False,
        'deployment_enabled':False,'ready_for_install':False,
        'artifacts':{name:{'sha256':hashlib.sha256((OUT/name).read_bytes()).hexdigest(),
                           'bytes':(OUT/name).stat().st_size} for name in artifacts},
        'model':{'name':'Helsinki-NLP/opus-mt-en-zh','source':'https://huggingface.co/Helsinki-NLP/opus-mt-en-zh',
            'local_only':True,'license_copy':'../models/opus-en-zh/original/LICENSE',
            'decoder_filter_validation':'decoder-filter-validation.json','sentence_refinement':'sentence-refinement.json'},
        'validation':validation,'font_validation':font_validation,'unit_tests_passed':int(test_count[1])}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    counts=summary['counts']
    state_path=BASE.parent/'client_patch/full/build-state.json'
    removed=state_path.exists() and json.loads(state_path.read_text(encoding='utf-8')).get('phase')=='restored-candidates-removed'
    candidate_note=('旧全量测试版已还原，旧 DAT 候选和备份已按要求删除以释放空间；本次修正保留为素材，尚未重新生成完整 DAT。'
                    if removed else '完整 DAT 的构建及安装状态以本机补丁包清单为准。')
    text=f'''# 全量汉化初稿（未部署）

详细操作见 [安装、还原与常见问题](../../docs/INSTALL.md)；源码发布准备见 [GitHub 发布说明](../../docs/RELEASING.md)。当前素材不能直接安装到游戏。

已扫描原始英文资源的 {counts['resources']:,} 个文本资源、{counts['fragments']:,} 个片段。
已生成 {counts['changed_fragments']:,} 个修改片段，分布于 {counts['changed_resources']:,} 个文本资源。
之前的界面、物品译文及两个任务译文继续优先保留。

**这是全量机器翻译初稿，尚未完成全量人工校对和游戏显示验证。**
机器翻译可能误译专有名词、漏掉含义或表达不自然；格式检查通过不能证明译文准确。
目前自动标记 {counts.get('fragments_with_qa_flags',0):,} 个片段供重点校对，其他机器译文也仍需审阅。

## 文件

- `review.csv`：全量中英对照、资源 ID、片段 ID、状态与疑点。建议用支持大文件的编辑器查看。
- `text-resources.sqlite3`：带原文哈希与译文哈希的二进制资源，以及完整结构化分段对照。
- `jobs.sqlite3`：去重翻译记忆、分段模板、既有译文及可恢复的处理记录。
- `fonts/records`：{fonts['font_resources']} 个字体、{fonts['texture_resources']} 个纹理资源，覆盖 {fonts['unicode_characters']:,} 个所需非ASCII字符。
- `quality-segments.jsonl`：自动检测到的可疑翻译单元；`review.csv` 的 QA 栏对应实际使用的片段。
- `manifest.json`、`validation.json`：数量、来源、哈希、结构校验和未部署状态。

没有英文的格式内容、调试标识、URL、键名、品牌、命令和姓名生成音节按用途保留。
保留范围的逐项原因写在对照与资源库中；其数量不能当成漏译句数。

## 验证与限制

所有文本资源均按已验证的原始英文资源核对源哈希、控制符、动态参数、分段边界与编解码往返。
原有字体字形指标与像素保留；为容纳全量汉字，必要时扩大纹理宽度。
本次字体扩展尚未实测，不应据此宣称所有界面已正常显示。

本目录保存工作区内的资源素材。{candidate_note}
`client_patch/deployment-policy.json` 继续禁止部署。本次素材重建只写工作区。游戏已按用户要求还原英文。
字体覆盖英文资源内的 45 个字体和 `client_general.dat` 中的 3 个字体，后续完整补丁需包含后者。
地图图片、商城网页不计入文本片段的翻译覆盖率，玩家使用范围见 [安装说明](../../docs/INSTALL.md)。

## 本地重建

```text
python localization/apply_full_corrections.py
python localization/full_context_corrections.py
python localization/fix_creation_feedback.py
python localization/fix_chat_selection_feedback.py
python localization/full_translate.py refresh
python localization/fix_commands_options_feedback.py
python localization/full_preflight.py
python localization/full_build.py
python localization/full_verify.py
python tools/verify_commands_options_feedback.py
python localization/build_fonts.py localization/full
python localization/full_font_verify.py
python localization/full_report.py
```

重建仅写工作区。既有人工译文应在 `jobs.sqlite3` 的 overrides 表按资源和片段 ID 修改，
保留 pieces 数量及所有协议控制符；不要直接改最终二进制文件。
模型与推理依赖保存在 `localization/models`、`vendor`、`cuda-libs`，不上传游戏文本。
'''
    (OUT/'README.md').write_text(text,encoding='utf-8')
    remaining=f'''# 汉化覆盖与仍需完成的工作

全量原始目录：{counts['resources']:,} 个文本资源、{counts['fragments']:,} 个片段。
本轮全量初稿已生成 {counts['changed_fragments']:,} 个修改片段。
去重翻译任务无 pending/error；无需翻译的技术与格式内容按原因保留。

**全量机器初稿已生成，不等于全量人工汉化已完成。**

仍需完成：

- 对机器译文进行人工校对，统一人名、地名、技能、装备和剧情术语。
- 优先处理对照中标记的 {counts.get('fragments_with_qa_flags',0):,} 个可疑片段，并复核未被标记的译文。
- 后续经用户授权部署后，检查真实界面的排版、换行、字体纹理与动态参数显示。
- 218 张地图已生成双语标注初版，仍需人工校对和游戏验证；商城网页需要独立方案，DAT 文本初稿不覆盖商城。

成果和全部对照在 [full/README.md](full/README.md)。旧 `output/batch-001` 保留。
当前没有部署，游戏保持英文。{candidate_note}
'''
    (BASE/'剩余汉化清单.md').write_text(remaining,encoding='utf-8')
    (OUT/'progress.json').write_text(json.dumps({'phase':'draft_artifacts_complete','pending_units':0,'error_units':0,
        'human_review_complete':False,'game_tested':False,'deployment_enabled':False},indent=2),encoding='utf-8')
    (OUT/'segment-summary.json').write_text(json.dumps(statuses,indent=2),encoding='utf-8')
    print('Full draft report saved; deployment remains disabled.',flush=True)


if __name__=='__main__':main()
