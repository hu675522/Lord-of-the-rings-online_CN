"""Read maps at additional angles to recover curved and diagonal labels."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'vendor'))
sys.path.insert(0,str(BASE.parent.parent))


def main():
    import cv2
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    from rapidfuzz.fuzz import ratio
    from localization.maps.match_labels import visual_key
    parser=argparse.ArgumentParser();parser.add_argument('--ids',default='');args=parser.parse_args()
    paths=sorted((BASE/'originals').glob('*.jpg'))
    if args.ids:paths=[p for p in paths if p.stem in args.ids.upper().split(',')]
    output=BASE/'ocr-augmented';output.mkdir(exist_ok=True)
    engine=RapidOCR(rec_model_path=str(BASE/'models/en_PP-OCRv4_rec_mobile.onnx'),det_limit_side_len=2048,
                    det_limit_type='max',max_side_len=3000,intra_op_num_threads=4,inter_op_num_threads=1)
    started=time.monotonic()
    for index,path in enumerate(paths,1):
        dest=output/(path.stem+'.json')
        if dest.exists():continue
        record=json.loads((BASE/'ocr'/(path.stem+'.json')).read_text(encoding='utf-8'))
        labels=[dict(r,ocr_angle=0) for r in record['labels']]
        img=cv2.imread(str(path));h,w=img.shape[:2]
        for angle in (-28.,28.,-50.):
            matrix=cv2.getRotationMatrix2D((w/2,h/2),angle,2.)
            corners=cv2.transform(np.array([[[0.,0.],[w,0.],[w,h],[0.,h]]],np.float32),matrix)[0]
            low=corners.min(axis=0);high=corners.max(axis=0)
            matrix[:,2]-=low
            rotated=cv2.warpAffine(img,matrix,(int(math.ceil(high[0]-low[0])),int(math.ceil(high[1]-low[1]))),
                                   flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT,borderValue=(220,205,160))
            inverse=cv2.invertAffineTransform(matrix)
            results,_=engine(rotated,use_cls=False,box_thresh=.4,text_score=.55)
            for polygon,text,score in results or []:
                back=cv2.transform(np.array([polygon],np.float32),inverse)[0]
                center=back.mean(axis=0)
                if not (3<center[0]<w-3 and 3<center[1]<h-3):continue
                back[:,0]=np.clip(back[:,0],0,w);back[:,1]=np.clip(back[:,1],0,h)
                if not visual_key(text):continue
                new={'polygon':back.tolist(),'text':text,'score':float(score),'ocr_angle':angle}
                duplicate=None
                for j,old in enumerate(labels):
                    a=np.array(old['polygon'],np.float32);b=back.astype(np.float32)
                    try:intersection,_=cv2.intersectConvexConvex(a,b)
                    except cv2.error:continue
                    area=min(abs(cv2.contourArea(a)),abs(cv2.contourArea(b)))
                    if area>0 and intersection/area>.65 and ratio(visual_key(text),visual_key(old['text']))>=60:
                        duplicate=j;break
                if duplicate is None:labels.append(new)
                else:
                    old=labels[duplicate]
                    if score>old['score']+.035 and len(visual_key(text))>=len(visual_key(old['text']))*.7:
                        labels[duplicate]=new
        record.update(labels=labels,ocr_angles=[0,-28,28,-50],original_label_count=len(record['labels']))
        dest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f"Angles {index}/{len(paths)} {path.stem}: {record['original_label_count']} -> {len(labels)}; {time.monotonic()-started:.1f}s",flush=True)


if __name__=='__main__':main()
