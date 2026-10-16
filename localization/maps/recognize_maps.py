"""Offline map-label OCR, preserving quadrilateral coordinates and confidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'vendor'))


def main():
    import cv2
    from rapidocr_onnxruntime import RapidOCR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--ids', default='')
    args = parser.parse_args()
    output = BASE / 'ocr'
    output.mkdir(exist_ok=True)
    engine = RapidOCR(rec_model_path=str(BASE / 'models/en_PP-OCRv4_rec_mobile.onnx'),
                      det_limit_side_len=2048, det_limit_type='max', max_side_len=3000,
                      intra_op_num_threads=4, inter_op_num_threads=1)
    images = sorted((BASE / 'originals').glob('*.jpg'))
    if args.ids:
        selected = {x.upper().removeprefix('0X') for x in args.ids.split(',')}
        images = [p for p in images if p.stem in selected]
    if args.limit:
        images = images[:args.limit]
    started = time.monotonic()
    for index, path in enumerate(images, 1):
        dest = output / (path.stem + '.json')
        if dest.exists():
            continue
        source = path.read_bytes()
        import numpy as np
        image = cv2.imdecode(np.frombuffer(source, np.uint8), cv2.IMREAD_COLOR)
        h, w = image.shape[:2]
        scale = min(2., 2800 / max(h, w))
        enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        result, elapsed = engine(enlarged, use_cls=False, box_thresh=.32, text_score=.30)
        labels = [{'text': text, 'score': float(score),
                   'polygon': [[round(float(x)/scale, 2), round(float(y)/scale, 2)] for x, y in polygon]}
                  for polygon, text, score in result or []]
        record = {'resource_id': '0x' + path.stem, 'source_image_sha256': hashlib.sha256(source).hexdigest(),
                  'engine': 'RapidOCR 1.4.4 / English PP-OCRv4', 'width': w, 'height': h,
                  'scale': scale, 'labels': labels, 'ocr_review_complete': False}
        dest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'OCR {index}/{len(images)} {path.stem}: {len(labels)} labels, {time.monotonic()-started:.1f}s', flush=True)


if __name__ == '__main__':
    main()
