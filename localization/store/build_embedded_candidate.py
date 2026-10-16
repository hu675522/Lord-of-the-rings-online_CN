"""Build a hash-bound CEF diagnostic candidate in the workspace; never install."""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[2]
EXPECTED_SHA='d131a79b23beaf580221df60c6308e339b72bfb93b39b2817b3d51828a8c39f2'
ADDRESS=0x140A36AED
BEFORE=bytes.fromhex('c785c001000014000000')
PORT=19222
# Replace the single, version-bound uncaught-exception stack-size assignment
# with a remote-debugging-port assignment. Default stack trace depth becomes 0.
AFTER=b'\xc7\x85'+struct.pack('<I',0x1bc)+struct.pack('<I',PORT)


def file_offset(raw,address):
    pe=struct.unpack_from('<I',raw,0x3c)[0]
    if raw[pe:pe+4]!=b'PE\0\0':raise ValueError('Invalid PE')
    machine,count=struct.unpack_from('<HH',raw,pe+4)
    if machine!=0x8664:raise ValueError('Only this x64 build is supported')
    optional=pe+24;size=struct.unpack_from('<H',raw,pe+20)[0]
    base=struct.unpack_from('<Q',raw,optional+24)[0];rva=address-base
    for i in range(count):
        section=optional+size+i*40
        virtual_size,virtual_address,raw_size,offset=struct.unpack_from('<IIII',raw,section+8)
        if virtual_address<=rva<virtual_address+min(virtual_size,raw_size):return offset+rva-virtual_address
    raise ValueError('Instruction outside file-backed sections')


def patch(raw):
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA:raise ValueError('Unsupported client version')
    offset=file_offset(raw,ADDRESS)
    if raw[offset:offset+len(BEFORE)]!=BEFORE:raise ValueError('Initialization instruction mismatch')
    result=raw[:offset]+AFTER+raw[offset+len(BEFORE):]
    if len(result)!=len(raw) or result[:offset]!=raw[:offset] or result[offset+10:]!=raw[offset+10:]:
        raise ValueError('Change outside intended instruction')
    return result,offset


def main():
    config=json.loads((ROOT/'data/original-archives.json').read_text(encoding='utf-8'))
    original=Path(config['game_directory'])/'x64/lotroclient64.exe';raw=original.read_bytes()
    result,offset=patch(raw)
    out=ROOT/'localization/store/embedded-candidate';out.mkdir(exist_ok=True)
    file=out/'lotroclient64.exe';file.write_bytes(result)
    plan={'source':str(original),'source_sha256':EXPECTED_SHA,'candidate_sha256':hashlib.sha256(result).hexdigest(),
        'candidate_file':file.name,'file_bytes':len(result),'file_offset':offset,
        'original_bytes':BEFORE.hex(),'candidate_bytes':AFTER.hex(),'cef_debug_port':PORT,
        'source_cef_version':'99.2.10+gfecf7ca+chromium-99.0.4844.51',
        'side_effect':'Uncaught JavaScript exception stack depth returns from 20 to its default 0.',
        'static_verification_passed':True,'game_start_verified':False,'loopback_binding_verified':False,
        'store_translation_verified':False,'installed':False,'deployment_enabled':False,
        'distribution_note':'Local research candidate only; do not distribute game executables.'}
    (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(plan,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
