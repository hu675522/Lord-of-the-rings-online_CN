"""Resumable public model download with normal Windows TLS validation."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import zipfile
from pip._vendor import truststore

truststore.inject_into_ssl()
ROOT=Path(__file__).resolve().parent/'models/opus-en-zh'
URL='https://object.pouta.csc.fi/Tatoeba-MT-models/eng-zho/opus-2020-07-17.zip'


def request(start,end):
    req=urllib.request.Request(URL,headers={'Range':f'bytes={start}-{end}',
                                           'User-Agent':'LOTRO-local-model-download/1.0'})
    return urllib.request.urlopen(req,timeout=90)


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    with request(0,0) as r:
        total=int(r.headers['Content-Range'].split('/')[-1])
        r.read()
    chunk_size=4*1024*1024
    chunks=ROOT/'download-chunks';chunks.mkdir(exist_ok=True)
    count=(total+chunk_size-1)//chunk_size
    def chunk(i):
        start=i*chunk_size;end=min(total,start+chunk_size)-1
        path=chunks/f'{i:04d}.bin'
        if path.exists() and path.stat().st_size==end-start+1:return path
        for attempt in range(5):
            try:
                with request(start,end) as r:
                    if r.status!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{total}':
                        raise ValueError('Range response mismatch')
                    data=r.read()
                if len(data)!=end-start+1:raise ValueError('Truncated range response')
                temporary=path.with_suffix('.part');temporary.write_bytes(data);temporary.replace(path)
                return path
            except Exception:
                if attempt==4:raise
                time.sleep(1+attempt)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(chunk,i) for i in range(count)]
        for n,job in enumerate(as_completed(jobs),1):
            job.result()
            if n%8==0 or n==count:print(f'Model chunks: {n}/{count}',flush=True)
    target=ROOT/'original.zip';stage=ROOT/'original.zip.part'
    digest=hashlib.sha256()
    with stage.open('wb') as out:
        for i in range(count):
            data=(chunks/f'{i:04d}.bin').read_bytes();out.write(data);digest.update(data)
    if stage.stat().st_size!=total:raise ValueError('Archive size mismatch')
    with zipfile.ZipFile(stage) as z:
        failure=z.testzip()
        if failure:raise ValueError('ZIP CRC failed: '+failure)
        print('Verified model archive members:',z.namelist(),flush=True)
    stage.replace(target)
    (ROOT/'download.json').write_text(json.dumps({'url':URL,'bytes':total,'sha256':digest.hexdigest(),
                                                'tls_verified':True,'zip_crc_verified':True},indent=2),encoding='utf-8')
    print('Official model archive ready.',flush=True)


if __name__=='__main__':main()
