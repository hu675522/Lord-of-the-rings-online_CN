import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack
from types import SimpleNamespace

from client_patch import full_manager as manager
from build_full_patch import write_pack,locations


class FullPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.package=self.root/'package';self.game=self.root/'game'
        (self.package/'work').mkdir(parents=True);self.game.mkdir()
        self.plan={'schema':2,'package_id':'fixture','candidate_build_complete':True,'all_workspace_checks_passed':True,'archives':[]}
        for i,name in enumerate(manager.NAMES):
            original=b'original-'+bytes([i]);candidate=b'candidate-'+bytes([i])
            (self.game/name).write_bytes(original);(self.package/'work'/name).write_bytes(candidate)
            self.plan['archives'].append({'name':name,'candidate':'work/'+name,
                'original_sha256':hashlib.sha256(original).hexdigest(),'patched_sha256':hashlib.sha256(candidate).hexdigest(),
                'original_size':len(original),'candidate_size':len(candidate)})
        manager.write_json(self.package/'install-plan.json',self.plan)
        manager.write_json(self.package/'deployment-policy.json',{'deployment_enabled':True})
        self.closed=patch.object(manager,'require_closed');self.closed.start()

    def tearDown(self):self.closed.stop();self.temp.cleanup()

    def original(self):
        for a in self.plan['archives']:self.assertEqual(manager.file_hash(self.game/a['name']),a['original_sha256'])

    def installed(self):
        for a in self.plan['archives']:self.assertEqual(manager.file_hash(self.game/a['name']),a['patched_sha256'])

    def test_portable_install_creates_backups_then_restores_with_policy_closed(self):
        manager.load_plan(self.package)
        manager.transition(self.package,self.plan,self.game);self.installed()
        manager.write_json(self.package/'deployment-policy.json',{'deployment_enabled':False})
        manager.transition(self.package,self.plan,self.game,restoring=True);self.original()
        self.assertFalse((self.package/'operation-journal.json').exists())

    def test_schema_three_backs_up_and_restores_general_font_archive(self):
        name='client_general.dat';original=b'general-original';candidate=b'general-font-fix'
        (self.game/name).write_bytes(original);(self.package/'work'/name).write_bytes(candidate)
        self.plan['schema']=3
        self.plan['archives'].append({'name':name,'candidate':'work/'+name,
            'original_sha256':hashlib.sha256(original).hexdigest(),'patched_sha256':hashlib.sha256(candidate).hexdigest(),
            'original_size':len(original),'candidate_size':len(candidate)})
        manager.write_json(self.package/'install-plan.json',self.plan)
        manager.load_plan(self.package)
        manager.transition(self.package,self.plan,self.game);self.installed()
        self.assertEqual(manager.backup_path(self.package,name).read_bytes(),original)
        manager.transition(self.package,self.plan,self.game,restoring=True);self.original()

    def test_schema_three_requires_general_archive_and_rejects_other_archives(self):
        self.plan['schema']=3
        manager.write_json(self.package/'install-plan.json',self.plan)
        with self.assertRaises(ValueError):manager.load_plan(self.package)
        self.plan['archives'].append(dict(self.plan['archives'][0],name='lotroclient64.exe'))
        manager.write_json(self.package/'install-plan.json',self.plan)
        with self.assertRaises(ValueError):manager.load_plan(self.package)

    def test_missing_or_disabled_policy_blocks_install_before_backups(self):
        for value in [False,None]:
            path=self.package/'deployment-policy.json'
            if value is None:path.unlink()
            else:manager.write_json(path,{'deployment_enabled':False})
            with self.assertRaisesRegex(ValueError,'暂不部署'):manager.transition(self.package,self.plan,self.game)
            self.original();self.assertFalse((self.package/'backups').exists())

    def test_unknown_updated_resource_blocks_all_changes(self):
        bad=self.game/manager.NAMES[-1];bad.write_bytes(b'new official version')
        with self.assertRaisesRegex(ValueError,'可能已更新'):manager.transition(self.package,self.plan,self.game)
        self.assertEqual(bad.read_bytes(),b'new official version')
        self.assertFalse((self.package/'backups').exists())

    def test_second_swap_failure_restores_preoperation_hashes(self):
        replace=manager.os.replace;failed=False
        def fail_once(source,target):
            nonlocal failed
            if not failed and Path(target)==self.game/manager.NAMES[1]:
                failed=True;raise PermissionError('injected second-swap failure')
            return replace(source,target)
        with patch.object(manager.os,'replace',side_effect=fail_once):
            with self.assertRaises(PermissionError):manager.transition(self.package,self.plan,self.game)
        self.original();self.assertFalse((self.package/'operation-journal.json').exists())
        self.assertFalse(list(self.game.glob('*.tmp')))

    def test_recover_after_interruption_restores_recorded_mixed_state(self):
        before={a['name']:a['original_sha256'] for a in self.plan['archives']}
        (self.package/'backups').mkdir()
        for a in self.plan['archives']:
            manager.backup_path(self.package,a['name']).write_bytes((self.game/a['name']).read_bytes())
        name=manager.NAMES[0];(self.game/name).write_bytes((self.package/'work'/name).read_bytes())
        manager.write_json(self.package/'operation-journal.json',{'package_id':'fixture','game_directory':str(self.game),'before':before})
        manager.write_json(self.package/'deployment-policy.json',{'deployment_enabled':False})
        manager.recover(self.package,self.plan,self.game);self.original()
        self.assertFalse((self.package/'operation-journal.json').exists())

    def test_corrupt_original_backup_blocks_restore_before_changes(self):
        manager.transition(self.package,self.plan,self.game)
        manager.backup_path(self.package,manager.NAMES[0]).write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError,'备份损坏'):manager.transition(self.package,self.plan,self.game,restoring=True)
        self.installed()

    def test_insufficient_disk_space_does_not_create_backups(self):
        with patch.object(manager,'check_space',side_effect=ValueError('空间不足')):
            with self.assertRaisesRegex(ValueError,'空间不足'):manager.transition(self.package,self.plan,self.game)
        self.original();self.assertFalse((self.package/'backups').exists())

    def test_candidate_path_escape_rejected(self):
        self.plan['archives'][0]['candidate']='../game/'+manager.NAMES[0]
        manager.write_json(self.package/'install-plan.json',self.plan)
        with self.assertRaisesRegex(ValueError,'候选路径'):manager.load_plan(self.package)
        self.original()

    def test_stream_pack_contains_resource_hash_and_payload(self):
        rid=0x25000001;raw=struct.pack('<I',rid)+b'content'
        path=self.root/'resources.pack';expected=write_pack(path,[(rid,raw)],1)
        content=path.read_bytes()
        self.assertEqual(content[:12],b'LTZHPAK1'+struct.pack('<I',1))
        self.assertEqual(content[12:20],struct.pack('<II',rid,len(raw)))
        self.assertEqual(content[20:52],hashlib.sha256(raw).digest())
        self.assertEqual(content[52:],raw)
        self.assertEqual(expected[rid],hashlib.sha256(raw).hexdigest())

    def test_extent_local_metadata_can_repeat_but_public_ids_cannot(self):
        class Reader:
            def __init__(self,path):self.path=path
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def entries(self):return [SimpleNamespace(resource_id=self.path)]
        with patch('build_full_patch.DatReader',Reader),ExitStack() as stack:
            self.assertIn(0xffff0001,locations(stack,[0xffff0001,0xffff0001]))
        with patch('build_full_patch.DatReader',Reader),ExitStack() as stack:
            with self.assertRaisesRegex(ValueError,'Duplicate public'):locations(stack,[0x25000001,0x25000001])


if __name__=='__main__':unittest.main()
