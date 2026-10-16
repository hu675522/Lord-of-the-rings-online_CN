import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import restore_audited_snapshot as tool
from client_patch.full_manager import NAMES, write_json


class AuditedRestoreTests(unittest.TestCase):
    def run_fixture(self, fail=False, changed=False, maps=False, no_cache_change=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / ('client_patch/test-20261015-maps' if maps else 'client_patch/full')
            game = root / 'game'
            (package / 'backups').mkdir(parents=True)
            game.mkdir()
            names = NAMES + (('client_general.dat',) if maps else ())
            plan = {'schema': 3 if maps else 2, 'package_id': 'full-draft-e93bb5ed8e8cd5c1' if maps else 'full-draft-ae9c605a20e9579d',
                    'candidate_build_complete': True, 'all_workspace_checks_passed': True, 'archives': []}
            observed = {}
            audit = {}
            for i, name in enumerate(names):
                original = b'original' + bytes([i])
                live = b'runtime' + bytes([i])
                (game / name).write_bytes(live)
                (package / 'backups' / (name + '.original')).write_bytes(original)
                digest = hashlib.sha256(original).hexdigest()
                plan['archives'].append({'name': name, 'candidate': 'work/' + name,
                    'original_size': len(original), 'original_sha256': digest, 'patched_sha256': digest})
                observed[name] = {'sha256': hashlib.sha256(live).hexdigest()}
                audit[name] = {'changed_public_resources': [{'id': '0x2505ba52'}] if i == 0 and not no_cache_change else []}
            write_json(package / 'install-plan.json', plan)
            write_json(package / 'installed-receipt.json', {'game_directory': str(game)})
            write_json(package / 'pre-restore-current-files.json', observed)
            write_json(package / 'runtime-public-resource-audit.json', audit)
            if changed:
                (game / NAMES[0]).write_bytes(b'new official update')
            real_replace = tool.os.replace
            def replace(source, target):
                if fail and Path(source).name == NAMES[1] + '.lotrozh-audited-restore.tmp':
                    raise PermissionError('injected swap failure')
                real_replace(source, target)
            with patch.object(tool, 'ROOT', root), patch.object(tool, 'require_closed'), patch.object(tool.os, 'replace', side_effect=replace):
                if fail or changed:
                    with self.assertRaises((PermissionError, ValueError)):
                        tool.restore()
                else:
                    tool.restore(package if maps else None)
            for i, name in enumerate(names):
                expected = (b'new official update' if changed and i == 0 else b'runtime' + bytes([i])) if fail or changed else b'original' + bytes([i])
                self.assertEqual((game / name).read_bytes(), expected)
            self.assertFalse(list(game.glob('*.tmp')))
            self.assertFalse((package / 'audited-restore-journal.json').exists())

    def test_audited_restore_verifies_and_removes_runtime_copies(self):
        self.run_fixture()

    def test_second_swap_failure_preserves_all_previous_live_files(self):
        self.run_fixture(fail=True)

    def test_new_change_after_audit_stops_before_copy(self):
        self.run_fixture(changed=True)

    def test_five_archive_map_snapshot_restores_general_too(self):
        self.run_fixture(maps=True)

    def test_runtime_metadata_only_changes_need_no_public_cache_change(self):
        self.run_fixture(maps=True,no_cache_change=True)
