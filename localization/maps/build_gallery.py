"""Generate a searchable, offline before/after gallery."""
import json
from pathlib import Path
BASE=Path(__file__).resolve().parent

def main():
    out=BASE/'bilingual-draft';manifest=json.loads((out/'manifest.json').read_text(encoding='utf8'));rows=[]
    for record in manifest['records']:
        name=f'{record["id"]:08X}';labels=json.loads((out/(name+'.layout.json')).read_text(encoding='utf8'))['labels']
        rows.append({'id':name,'title':max(labels,key=lambda r:r['font_size'])['chinese'],
            'labels':[[r.get('source',r['text']),r['chinese']] for r in labels]})
    data=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>中土地图 · 双语预览</title>
<style>*{box-sizing:border-box}body{margin:0;background:#171c1d;color:#eee4cf;font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif}header{padding:24px 4vw;background:#27312f;position:sticky;top:0;z-index:1}h1{font-size:24px;margin:0}p{margin:4px 0;color:#c4cabb}input{padding:10px;margin-top:12px;width:min(650px,100%);background:#111b1a;color:#fff;border:1px solid #869083;border-radius:5px}main{padding:24px 4vw;display:grid;gap:20px;grid-template-columns:repeat(auto-fill,minmax(290px,1fr))}.card{padding:0;color:inherit;background:#293230;border:1px solid #536158;border-radius:8px;overflow:hidden;text-align:left;cursor:pointer;font:inherit}.card img{width:100%;aspect-ratio:4/3;object-fit:contain;background:#111;display:block}.card div{padding:9px 14px}.card small{color:#b3c1b0}dialog{width:min(1460px,98vw);height:95vh;background:#1b2423;color:#eee4cf;border:1px solid #7c8b79;border-radius:8px}dialog::backdrop{background:#000d}.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap}dialog button{background:#394d44;color:#fff;border:1px solid #80937d;border-radius:5px;padding:8px 14px;cursor:pointer}.view{display:grid;grid-template-columns:minmax(0,1fr) 250px;gap:16px;margin-top:12px}#big{max-width:100%;max-height:76vh;object-fit:contain;touch-action:none;user-select:none}#names{overflow:auto;max-height:76vh;font-size:13px}#names div{border-bottom:1px solid #526050;padding:6px}#names span{display:block;color:#b9c9b4}#count{float:right}@media(max-width:760px){.view{grid-template-columns:1fr}#names{max-height:20vh}}</style>
<header><span id="count"></span><h1>中土地图 · 中英双语预览</h1><p>点击放大，按住大图对照英文原图。← → 翻页。</p><p>本地初版 · 未部署 · 尚未进游戏验证；专名译法仍可校对。</p><input id="query" placeholder="搜索中文、英文或资源编号" aria-label="搜索地图"></header><main id="grid"></main>
<dialog id="viewer"><div class="toolbar"><button id="close">关闭</button><button id="prev">上一张</button><button id="next">下一张</button><strong id="heading"></strong></div><div class="view"><div><img id="big" draggable="false" alt="双语地图大图"></div><div id="names"></div></div></dialog>
<script>const maps=DATA;let filtered=maps,index=0;const q=document.querySelector('#query'),grid=document.querySelector('#grid'),dlg=document.querySelector('#viewer'),big=document.querySelector('#big');
function draw(){grid.replaceChildren();filtered=maps.filter(r=>(r.id+' '+r.labels.flat().join(' ')).toLowerCase().includes(q.value.trim().toLowerCase()));document.querySelector('#count').textContent=filtered.length+' / '+maps.length+' 张';for(const r of filtered){const card=document.createElement('button');card.className='card';const image=document.createElement('img');image.src=r.id+'.png';image.loading='lazy';image.alt=r.title;const text=document.createElement('div');text.textContent=r.title+' ';const small=document.createElement('small');small.textContent='0x'+r.id;text.append(small);card.append(image,text);card.onclick=()=>{index=filtered.indexOf(r);show();dlg.showModal()};grid.append(card)}}
function show(){const r=filtered[index];big.src=r.id+'.png';document.querySelector('#heading').textContent=r.title+' · 0x'+r.id;const names=document.querySelector('#names');names.replaceChildren();for(const [en,zh] of r.labels){const item=document.createElement('div');item.textContent=zh;const english=document.createElement('span');english.textContent=en;item.append(english);names.append(item)}}
function step(n){index=(index+n+filtered.length)%filtered.length;show()}q.oninput=draw;document.querySelector('#close').onclick=()=>dlg.close();document.querySelector('#prev').onclick=()=>step(-1);document.querySelector('#next').onclick=()=>step(1);document.addEventListener('keydown',e=>{if(dlg.open&&e.key==='ArrowLeft')step(-1);if(dlg.open&&e.key==='ArrowRight')step(1)});big.onpointerdown=e=>{big.setPointerCapture(e.pointerId);big.src='../originals/'+filtered[index].id+'.jpg'};function restore(){big.src=filtered[index].id+'.png'}big.onpointerup=restore;big.onpointercancel=restore;draw();</script></html>'''.replace('DATA',data)
    progress=BASE/'progress.json'
    if progress.exists() and json.loads(progress.read_text(encoding='utf8')).get('deployed'):
        html=html.replace('本地初版 · 未部署 · 尚未进游戏验证；专名译法仍可校对。','本地初版 · 测试版已部署 · 游戏内效果待确认；专名译法仍可校对。')
    (out/'index.html').write_text(html,encoding='utf8');print(len(rows),'maps in offline gallery')

if __name__=='__main__':main()
