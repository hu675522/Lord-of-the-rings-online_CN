"""Read-only PE inspection of the installed embedded browser; never executes it.

Optional research dependencies live under artifacts/store-research/vendor.
The report contains executable metadata and initialization code, no profiles.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'artifacts/store-research/vendor'))
import capstone
import pefile


def inspect(path):
    raw=path.read_bytes(); pe=pefile.PE(data=raw)
    if pe.FILE_HEADER.Machine != 0x8664:
        raise ValueError('This inspection expects the x64 client')
    base=pe.OPTIONAL_HEADER.ImageBase
    imports={i.address:i.name.decode('ascii') for d in pe.DIRECTORY_ENTRY_IMPORT
             for i in d.imports if i.name}
    wanted={a for a,n in imports.items() if n=='cef_initialize'}
    sites=[]; thunks=set(); executable=[]
    for section in pe.sections:
        if not section.Characteristics & 0x20000000: continue
        data=section.get_data(); start=base+section.VirtualAddress
        executable.append((start,data))
        for match in re.finditer(b'\xff[\x15\x25]',data):
            p=match.start()
            if p+6>len(data):continue
            target=start+p+6+struct.unpack_from('<i',data,p+2)[0]
            if target in wanted:
                if data[p+1]==0x25:thunks.add(start+p)
                else:sites.append(start+p)
    for start,data in executable:
        for match in re.finditer(b'\xe8',data):
            p=match.start()
            if p+5<=len(data) and start+p+5+struct.unpack_from('<i',data,p+1)[0] in thunks:
                sites.append(start+p)
    dis=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    functions=[]
    for site in sites:
        entry=next(e for e in pe.DIRECTORY_ENTRY_EXCEPTION
                   if base+e.struct.BeginAddress<=site<base+e.struct.EndAddress)
        begin=entry.struct.BeginAddress; size=entry.struct.EndAddress-begin
        if size>65536:raise ValueError('Unexpected initialization function size')
        code=pe.get_data(begin,size)
        functions.append({'call_address':hex(site),'function_start':hex(base+begin),
            'function_bytes':size,'instructions':[
                f'{a:#x}: {mnemonic} {operands}' for a,_,mnemonic,operands
                in dis.disasm_lite(code,base+begin)]})
    callers=[]
    starts={int(f['function_start'],16) for f in functions}
    for start,data in executable:
        for match in re.finditer(b'\xe8',data):
            p=match.start()
            if p+5>len(data) or start+p+5+struct.unpack_from('<i',data,p+1)[0] not in starts:continue
            site=start+p
            entry=next(e for e in pe.DIRECTORY_ENTRY_EXCEPTION if base+e.struct.BeginAddress<=site<base+e.struct.EndAddress)
            begin=entry.struct.BeginAddress;size=entry.struct.EndAddress-begin
            if size>65536:raise ValueError('Unexpected caller size')
            callers.append({'call_address':hex(site),'function_start':hex(base+begin),'instructions':[
                f'{a:#x}: {mnemonic} {operands}' for a,_,mnemonic,operands
                in dis.disasm_lite(pe.get_data(begin,size),base+begin)]})
    strings=[]
    for needle in [b'twebbrowser',b'JavaScriptExecuted',b'scriptDebuggingPort',b'remote-debugging-port']:
        positions=[m.start() for m in re.finditer(re.escape(needle),raw)]
        strings.append({'text':needle.decode(),'file_offsets':[hex(p) for p in positions]})
    return {'file':str(path),'sha256':hashlib.sha256(raw).hexdigest(),
            'cef_initialize_calls':functions,'cef_initialize_iat':[hex(a) for a in wanted],
            'cef_initialize_thunks':[hex(a) for a in thunks], 'string_evidence':strings,
            'initialization_callers':callers,
            'read_only':True,'game_executed':False,'profiles_read':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,required=True)
    args=parser.parse_args()
    report=inspect(args.game_dir/'x64/lotroclient64.exe')
    out=ROOT/'artifacts/store-research';out.mkdir(exist_ok=True)
    (out/'cef-initialization.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('cef_initialize calls:',len(report['cef_initialize_calls']))
    for function in report['cef_initialize_calls']:
        print('\n'.join(function['instructions']))
    for function in report['initialization_callers']:
        print('CALLER:',function['function_start'])
        print('\n'.join(function['instructions']))


if __name__=='__main__':main()
