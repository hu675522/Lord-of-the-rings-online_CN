"""Compare the exact map-test installation to its candidates before recovery."""
from contextlib import ExitStack
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build_full_patch import locations,payload_hash
from client_patch.full_manager import load_plan,file_hash,write_json,archive_names


def main(package=None):
    package=Path(package or ROOT/'client_patch/test-20261015-maps').resolve()
    if not package.is_relative_to((ROOT/'client_patch').resolve()):raise ValueError('Package outside workspace')
    plan=load_plan(package)
    if plan['package_id'] not in {'full-draft-e93bb5ed8e8cd5c1','full-draft-b38987d4c23ab456','full-draft-bf681ae09630df99', 'full-draft-1f21b7a124c7059b', 'full-draft-45f998a2ad1f82ea'}:raise ValueError('Wrong test snapshot')
    game=Path(json.loads((package/'installed-receipt.json').read_text(encoding='utf8'))['game_directory'])
    observed={};audit={n:{'changed_public_resources':[]} for n in archive_names(plan)}
    for row in plan['archives']:
        if file_hash(package/row['candidate'])!=row['patched_sha256']:raise ValueError('Candidate changed')
        observed[row['name']]={'sha256':file_hash(game/row['name'])}
    groups=[['client_local_English.dat'],['client_surface.dat','client_surface_aux_1.datx','client_surface_aux_2.datx'],['client_general.dat']]
    for names in groups:
        print('Auditing public resources:',names[0],flush=True)
        with ExitStack() as stack:
            before=locations(stack,[package/'work'/n for n in names]);after=locations(stack,[game/n for n in names])
            old={r for r in before if r<0xff000000};new={r for r in after if r<0xff000000}
            if old!=new:raise ValueError('Public resource IDs changed')
            changed=[]
            for i,rid in enumerate(sorted(old),1):
                a,e=before[rid];b,f=after[rid]
                left=payload_hash(a.content(e,validate_identifier=False));right=payload_hash(b.content(f,validate_identifier=False))
                if left!=right:changed.append({'id':f'0x{rid:08x}','candidate_sha256':left,'runtime_sha256':right})
                if i%250000==0:print('Audited:',i,flush=True)
            allowed={0x2505ba52} if names[0]=='client_local_English.dat' else set()
            if not {int(v['id'],16) for v in changed}<=allowed:raise ValueError('Unexpected public resource changes: '+str(changed))
            audit[names[0]].update(changed_public_resources=changed,public_resources_verified=len(old),public_id_set_unchanged=True)
            print('Verified',len(old),'public resources;',len(changed),'known runtime cache changes',flush=True)
    for name in observed:
        if file_hash(game/name)!=observed[name]['sha256']:raise ValueError('Live game changed during audit')
    write_json(package/'pre-restore-current-files.json',observed)
    write_json(package/'runtime-public-resource-audit.json',audit)
    print('Exact runtime snapshot audited; no game files changed.',flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path)
    main(parser.parse_args().package)
