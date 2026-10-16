from io import BytesIO
import hashlib,json,struct,tempfile,unittest
from pathlib import Path
from PIL import Image
from lotro_zh.map_resource import jpeg_texture
from localization.maps.render_maps import render,overlap
from localization.maps.verify_maps import load_payloads
from localization.maps.prepare_labels import merge_labels


class MapTests(unittest.TestCase):
    def sample(self):
        out=BytesIO();Image.new('RGB',(200,140),'tan').save(out,format='JPEG');jpeg=out.getvalue()
        return struct.pack('<6I',0x41001234,15,0,0,500,len(jpeg))+jpeg

    def test_jpeg_container_accepts_native_zero_dimensions(self):
        rid,size,jpeg=jpeg_texture(self.sample())
        self.assertEqual((rid,size),(0x41001234,(200,140)))
        self.assertEqual(Image.open(BytesIO(jpeg)).format,'JPEG')

    def test_truncation_and_wrong_dimension_are_rejected(self):
        with self.assertRaises(ValueError):jpeg_texture(self.sample()[:-10])
        raw=bytearray(self.sample());struct.pack_into('<I',raw,8,201)
        with self.assertRaises(ValueError):jpeg_texture(raw)

    def test_native_manifest_rejects_tampering_and_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);raw=self.sample();(base/'map.bin').write_bytes(raw)
            row={'id':0x41001234,'file':'map.bin','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'group':'client_local_English.dat','image_size':[200,140]}
            path=base/'manifest.json'
            path.write_text(json.dumps({'maps':1,'records':[row]}),encoding='utf8')
            self.assertEqual(len(load_payloads(path)[1]),1)
            (base/'map.bin').write_bytes(raw[:-2])
            with self.assertRaises(ValueError):load_payloads(path)
            row['file']='../outside.bin';path.write_text(json.dumps({'maps':1,'records':[row]}),encoding='utf8')
            with self.assertRaises(ValueError):load_payloads(path)

    def test_render_preserves_english_and_all_pixels_outside_annotations(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);src=base/'source.jpg';Image.new('RGB',(260,180),'tan').save(src)
            polygon=[[70,60],[180,60],[180,85],[70,85]]
            labels=[{'text':'English','polygon':polygon,'chinese':'','label_id':'source'},
                {'text':'English','polygon':polygon,'chinese':'中文测试','label_id':'translation','font_size':16}]
            before=src.read_bytes();report,jpeg=render(src,labels,base/'output.png')
            self.assertEqual(src.read_bytes(),before)
            self.assertTrue(report['pixels_outside_annotation_boxes_unchanged'])
            self.assertEqual(overlap(report['labels'][0]['annotation_box'],(70,60,180,85)),0)
            self.assertEqual(Image.open(BytesIO(jpeg)).size,(260,180))

    def test_split_name_merges_but_separate_places_do_not(self):
        def label(source,top):return {'source':source,'text':source,'chinese':'占位',
            'polygon':[[80,top],[180,top],[180,top+15],[80,top+15]],'font_size':14,'label_id':source}
        rows=merge_labels([label('Paths',30),label('The Dead',49),label('Rivendell',125)],{'Paths of the Dead':'亡者之路'})
        self.assertEqual(len(rows),2)
        self.assertIn('亡者之路',[r['chinese'] for r in rows])


if __name__=='__main__':unittest.main()
