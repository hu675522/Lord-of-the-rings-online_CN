"""Convert official numeric weights; never execute scripts from the model ZIP."""
import json
import os
from pathlib import Path
import sys
import zipfile

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'vendor'))
DLL_HANDLES=[]
DLL_PATHS=[]
for path in (BASE/'cuda-libs/nvidia').glob('*/bin'):
    DLL_HANDLES.append(os.add_dll_directory(str(path)))
    DLL_PATHS.append(str(path))
os.environ['PATH']=os.pathsep.join(DLL_PATHS+[os.environ.get('PATH','')])
import ctranslate2
import sentencepiece as spm
import yaml


def main():
    root=BASE/'models/opus-en-zh'
    raw=root/'original';raw.mkdir(exist_ok=True)
    with zipfile.ZipFile(root/'original.zip') as z:
        for name in z.namelist():
            if name.endswith(('.npz','.yml','.spm')) or name in ('README.md','LICENSE'):
                if Path(name).name!=name:raise ValueError('Unexpected archive member path')
                target=(raw/name).resolve()
                if not target.is_relative_to(raw.resolve()):raise ValueError('Extraction path outside model folder')
                if not target.exists():target.write_bytes(z.read(name))
    decoder=yaml.safe_load((raw/'decoder.yml').read_text(encoding='utf-8'))
    for filename in decoder['models']+decoder['vocabs']:
        if not (raw/filename).resolve().is_relative_to(raw.resolve()):raise ValueError('Decoder path outside model folder')
    from ctranslate2.converters.opus_mt import OpusMTConverter
    converted=root/'ct2-int8'
    if not (converted/'model.bin').exists():
        OpusMTConverter(str(raw)).convert(str(converted),quantization='int8')
    vocab=yaml.safe_load((raw/decoder['vocabs'][0]).read_text(encoding='utf-8'))
    language='>>cmn_Hans<<'
    if language not in vocab:raise ValueError('Simplified Mandarin language token missing')
    source=spm.SentencePieceProcessor(model_file=str(raw/'source.spm'))
    target=spm.SentencePieceProcessor(model_file=str(raw/'target.spm'))
    engine=ctranslate2.Translator(str(converted),device='cuda',compute_type='int8_float16')
    samples=['The quest is complete.','This item is bound to your account.',
             'Retrieve a fancy Ordâkhai blade from the camp of Kôth Rau.',
             'You must leave combat before changing your equipment.']
    tokens=[[language]+source.encode(s,out_type=str) for s in samples]
    results=engine.translate_batch(tokens,beam_size=1,max_decoding_length=256)
    report=[]
    for text,result in zip(samples,results):
        value=target.decode(result.hypotheses[0]);report.append({'source':text,'chinese':value});print(text,'=>',value,flush=True)
    (root/'runtime.json').write_text(json.dumps({'engine':'ctranslate2','version':ctranslate2.__version__,
        'device':'cuda','compute_type':'int8_float16','language_token':language,
        'model':str(converted),'samples':report},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Local GPU translation engine ready.',flush=True)


if __name__=='__main__':main()
