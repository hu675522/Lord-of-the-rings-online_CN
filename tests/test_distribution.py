import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from distribution import delta, manage


class DistributionTests(unittest.TestCase):
    def fixture(self, root):
        original = root / 'original'; candidate = root / 'candidate'; packed = root / 'difference.zip'
        original.write_bytes(b'a' * delta.BLOCK + b'b' * delta.BLOCK)
        candidate.write_bytes(b'a' * delta.BLOCK + b'c' * delta.BLOCK + b'new tail')
        meta = delta.build(original, candidate, packed)
        return original, candidate, packed, meta

    def test_unicode_path_reconstructs_changed_and_appended_blocks(self):
        with tempfile.TemporaryDirectory(prefix='游戏 空格 ') as temp:
            root = Path(temp); original, candidate, packed, meta = self.fixture(root)
            target = root / '汉化.dat'; delta.apply(original, packed, target, meta)
            self.assertEqual(target.read_bytes(), candidate.read_bytes())
            self.assertEqual([r['index'] for r in meta['blocks']], [1, 2])

    def test_truncated_candidate_and_changed_last_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original, candidate, packed, _ = self.fixture(root)
            candidate.write_bytes(b'xyz')
            meta = delta.build(original, candidate, packed)
            target = root / 'result'; delta.apply(original, packed, target, meta)
            self.assertEqual(target.read_bytes(), b'xyz')

    def test_rejects_wrong_source_before_creating_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original, _, packed, meta = self.fixture(root)
            original.write_bytes(b'wrong'); target = root / 'result'
            with self.assertRaisesRegex(ValueError, 'version mismatch'):
                delta.apply(original, packed, target, meta)
            self.assertFalse(target.exists())

    def test_corrupt_block_removes_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original, _, packed, meta = self.fixture(root)
            with zipfile.ZipFile(packed) as source:
                contents = {n: source.read(n) for n in source.namelist()}
            contents['blocks/1.bin'] = b'z' * delta.BLOCK
            with zipfile.ZipFile(packed, 'w') as out:
                for name, data in contents.items(): out.writestr(name, data)
            target = root / 'result'
            with self.assertRaisesRegex(ValueError, 'checksum'):
                delta.apply(original, packed, target, meta)
            self.assertFalse(target.exists()); self.assertFalse((root / 'result.building').exists())

    def test_never_overwrites_existing_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); original, _, packed, meta = self.fixture(root)
            target = root / 'result'; target.write_bytes(b'personal')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                delta.apply(original, packed, target, meta)
            self.assertEqual(target.read_bytes(), b'personal')

    def test_cleanup_requires_restoration_and_same_game(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); game = root / 'game'; game.mkdir()
            (root / 'installed-receipt.json').write_text(json.dumps({'state':'installed-for-testing','game_directory':str(game)}))
            backup = root / 'backups/keep.original'; backup.parent.mkdir(); backup.write_bytes(b'keep')
            with patch.object(manage.core, 'require_closed'):
                with self.assertRaisesRegex(ValueError, 'Restore'):
                    manage.cleanup(root, {'archives':[]}, game)
            self.assertTrue(backup.exists())

    def test_full_portable_flow_keeps_unrelated_files_and_reinstalls_after_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='自定义 路径 ') as temp:
            base = Path(temp); root = base / '汉化包'; game = base / '游戏 安装'
            root.mkdir(); game.mkdir(); rows = []
            for name in manage.core.NAMES + ('client_general.dat',):
                source = game / name; source.write_bytes(b'en:' + name.encode() + b'a' * 120)
                candidate = base / name; candidate.write_bytes(b'zh:' + name.encode() + b'b' * 160)
                packed = root / 'payload' / (name + '.zip')
                meta = delta.build(source, candidate, packed)
                row = {k: meta[k] for k in ('original_size', 'candidate_size', 'original_sha256', 'patched_sha256')}
                row.update(name=name, candidate='work/' + name, delta='payload/' + name + '.zip', delta_sha256=delta.digest(packed))
                rows.append(row)
            plan = {'schema': 3, 'package_id': 'fixture', 'candidate_build_complete': True,
                    'all_workspace_checks_passed': True, 'distribution_format': 'sha256-block-delta-v1', 'archives': rows}
            (root / 'install-plan.json').write_text(json.dumps(plan))
            (root / 'deployment-policy.json').write_text('{"deployment_enabled":true}')
            unrelated = game / 'other-plugin.txt'; unrelated.write_bytes(b'keep')
            with patch.object(manage.core, 'require_closed'):
                manage.run(root, 'install', game)
                for row in rows: self.assertEqual(delta.digest(game / row['name']), row['patched_sha256'])
                manage.run(root, 'restore', game)
                for row in rows: self.assertEqual(delta.digest(game / row['name']), row['original_sha256'])
                manage.run(root, 'cleanup', game)
                self.assertFalse(list((root / 'work').iterdir()))
                self.assertFalse(list((root / 'backups').iterdir()))
                manage.run(root, 'install', game)
            self.assertEqual(unrelated.read_bytes(), b'keep')


if __name__ == '__main__': unittest.main()
