"""Create local, numbered source crops for OCR and translation review."""
import argparse,json,math
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from render_maps import bounds

BASE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['pending','noise']);args=parser.parse_args()
    if args.kind=='pending':rows=json.loads((BASE/'pending-labels.json').read_text(encoding='utf8'))
    else:
        data=json.loads((BASE/'label-matches.json').read_text(encoding='utf8'))
        rows=[dict(v,map=r['resource_id']) for r in data['records'] for v in r['labels'] if v['status']=='ocr-noise-review']
    out=BASE/'qa-crops';out.mkdir(exist_ok=True)
    (out/(args.kind+'-index.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    font=ImageFont.truetype(r'C:\Windows\Fonts\consola.ttf',12)
    for start in range(0,len(rows),36):
        sheet=Image.new('RGB',(1440,1080),'#dddddd');draw=ImageDraw.Draw(sheet)
        for i,row in enumerate(rows[start:start+36]):
            x=(i%4)*360;y=(i//4)*120;rid=row['map'][2:];im=Image.open(BASE/'originals'/(rid+'.jpg'))
            a=bounds(row['polygon']);crop=im.crop((max(0,a[0]-12),max(0,a[1]-12),min(im.width,a[2]+12),min(im.height,a[3]+12)))
            crop.thumbnail((350,91));sheet.paste(crop,(x,y+24))
            draw.text((x+3,y+2),f'{start+i}: {rid} {row["text"][:26]}',font=font,fill='black')
        sheet.save(out/(args.kind+f'-{start//36+1}.png'))
    print(args.kind,len(rows),'crops')

if __name__=='__main__':main()
