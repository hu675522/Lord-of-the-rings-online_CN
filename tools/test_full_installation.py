"""Exercise full-size install/restore using workspace-only game copies.

The fixture package alone has a temporary enabled policy. Real package and live
game policies are not changed. A successful run removes only its own fixture.
"""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from client_patch import full_manager as manager


def main():
    package=ROOT/'client_patch/full'
    plan=manager.load_plan(package)
    fixture=(ROOT/'.test-tmp/full-size-installation').resolve()
    allowed=(ROOT/'.test-tmp').resolve()
    if not fixture.is_relative_to(allowed) or fixture.exists():raise ValueError('Fixture target must be new and inside .test-tmp')
    fixture.mkdir(parents=True)
    test_package=fixture/'package';game=fixture/'game'
    test_package.mkdir();game.mkdir()
    manager.write_json(test_package/'install-plan.json',plan)
    manager.write_json(test_package/'deployment-policy.json',{'deployment_enabled':True,'scope':'workspace test fixture only'})
    (test_package/'work').mkdir()
    for archive in plan['archives']:
        name=archive['name'];print('Preparing full-size game fixture:',name,flush=True)
        # Separate copies keep this test independent of the actual candidates.
        shutil.copyfile(ROOT/'client_patch/backups'/(name+'.original'),game/name)
        # Candidate files are read-only inputs to transition; link creation is
        # confined to workspace test data and cannot change the source bytes.
        __import__('os').link(package/archive['candidate'],test_package/archive['candidate'])
    with patch.object(manager,'require_closed'):
        manager.transition(test_package,plan,game)
        installed=manager.inspect_game(test_package,plan,game)
        if any(r['state']!='full_candidate' for r in installed.values()):raise ValueError('Full-size install verification failed')
        manager.write_json(test_package/'deployment-policy.json',{'deployment_enabled':False})
        manager.transition(test_package,plan,game,restoring=True)
        restored=manager.inspect_game(test_package,plan,game)
        if any(r['state']!='original' for r in restored.values()):raise ValueError('Full-size restore verification failed')
    real_policy=json.loads((package/'deployment-policy.json').read_text(encoding='utf-8'))
    if real_policy.get('deployment_enabled') is not False:raise ValueError('Real deployment policy changed')
    report={'scope':'workspace-only full-size copies','all_four_candidate_hashes_verified_after_install':True,
            'all_four_original_hashes_verified_after_restore':True,'installed':installed,'restored':restored,
            'real_package_deployment_enabled':False,'live_game_modified':False,'game_rendering_verified':False,
            'checked_utc':datetime.now(timezone.utc).isoformat()}
    manager.write_json(package/'installation-simulation.json',report)
    # Check the absolute removal target immediately before recursive cleanup.
    resolved=fixture.resolve()
    if resolved!=allowed/'full-size-installation' or not resolved.is_relative_to(allowed):raise ValueError('Unsafe fixture cleanup target')
    shutil.rmtree(resolved)
    print('Full-size installation and restoration passed; workspace fixture removed.',flush=True)


if __name__=='__main__':main()
