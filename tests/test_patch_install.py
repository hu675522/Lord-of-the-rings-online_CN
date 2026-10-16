import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("patch_manage", Path(__file__).resolve().parents[1] / "client_patch/manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.install = self.root / "game"
        self.install.mkdir()
        self.plan = {"task": "Test", "install_directory": str(self.install), "archives": []}
        for i, name in enumerate(sorted(manage.ALLOWED)):
            backup = self.root / (name + ".original")
            candidate = self.root / (name + ".candidate")
            backup.write_bytes(b"original " + bytes((i,)))
            candidate.write_bytes(b"patched " + bytes((i,)))
            (self.install / name).write_bytes(backup.read_bytes())
            self.plan["archives"].append({"name": name, "backup": str(backup), "candidate": str(candidate),
                                          "original_sha256": manage.file_hash(backup), "patched_sha256": manage.file_hash(candidate)})
        self.closed = patch.object(manage, "require_closed")
        self.closed.start()
        self.location = patch.object(manage, "PATCH", self.root)
        self.location.start()

    def tearDown(self):
        self.closed.stop()
        self.location.stop()
        self.temp.cleanup()

    def assert_originals(self):
        for entry in self.plan["archives"]:
            self.assertEqual(manage.file_hash(self.install / entry["name"]), entry["original_sha256"])

    def test_install_and_restore_all_extents(self):
        manage.transition(self.plan)
        for entry in self.plan["archives"]:
            self.assertEqual(manage.file_hash(self.install / entry["name"]), entry["patched_sha256"])
        manage.transition(self.plan, restoring=True)
        self.assert_originals()

    def test_refuses_unknown_updated_game_file_before_any_copy(self):
        bad = self.plan["archives"][-1]
        (self.install / bad["name"]).write_bytes(b"new game update")
        with self.assertRaisesRegex(ValueError, "可能已经更新"):
            manage.transition(self.plan)
        for entry in self.plan["archives"][:-1]:
            self.assertEqual(manage.file_hash(self.install / entry["name"]), entry["original_sha256"])
        self.assertEqual((self.install / bad["name"]).read_bytes(), b"new game update")

    def test_failed_second_replace_rolls_back_first_and_cleans_staging(self):
        real_replace = manage.os.replace
        second = self.plan["archives"][1]["name"]
        failed = False

        def replace(source, target):
            nonlocal failed
            if not failed and Path(target).name == second:
                failed = True
                raise PermissionError("simulated locked file")
            return real_replace(source, target)

        with patch.object(manage.os, "replace", side_effect=replace):
            with self.assertRaises(PermissionError):
                manage.transition(self.plan)
        self.assert_originals()
        self.assertEqual(list(self.install.glob("*.tmp")), [])

    def test_game_process_blocks_install_without_touching_files(self):
        self.closed.stop()
        with patch.object(manage, "game_processes", return_value=["lotroclient64.exe"]):
            with self.assertRaisesRegex(RuntimeError, "退出游戏"):
                manage.transition(self.plan)
        self.closed.start()
        self.assert_originals()

    def prepare_previous_version(self):
        for entry in self.plan["archives"]:
            previous = self.root / (entry["name"] + ".previous")
            previous.write_bytes(b"previous " + entry["name"].encode())
            entry.update(previous_sha256=manage.file_hash(previous), previous_candidate=str(previous))
            (self.install / entry["name"]).write_bytes(previous.read_bytes())

    def test_user_deployment_lock_blocks_install_but_allows_restore(self):
        (self.root / 'deployment-policy.json').write_text('{"deployment_enabled":false}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, "暂不部署"):
            manage.transition(self.plan)
        self.assert_originals()
        manage.transition(self.plan, restoring=True)
        self.assert_originals()

    def test_upgrade_previous_version_then_restore_originals(self):
        self.prepare_previous_version()
        manage.transition(self.plan)
        for entry in self.plan["archives"]:
            self.assertEqual(manage.file_hash(self.install / entry["name"]), entry["patched_sha256"])
        manage.transition(self.plan, restoring=True)
        self.assert_originals()

    def test_failed_upgrade_rolls_back_to_previous_not_original(self):
        self.prepare_previous_version()
        real_replace = manage.os.replace
        second = self.plan["archives"][1]["name"]
        failed = False

        def replace(source, target):
            nonlocal failed
            if not failed and Path(target).name == second:
                failed = True
                raise PermissionError("simulated upgrade lock")
            return real_replace(source, target)

        with patch.object(manage.os, "replace", side_effect=replace):
            with self.assertRaises(PermissionError):
                manage.transition(self.plan)
        for entry in self.plan["archives"]:
            self.assertEqual(manage.file_hash(self.install / entry["name"]), entry["previous_sha256"])

    def test_corrupt_previous_copy_blocks_upgrade_before_changes(self):
        self.prepare_previous_version()
        Path(self.plan["archives"][-1]["previous_candidate"]).write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "上版回滚副本"):
            manage.transition(self.plan)
        for entry in self.plan["archives"]:
            self.assertEqual(manage.file_hash(self.install / entry["name"]), entry["previous_sha256"])


if __name__ == "__main__":
    unittest.main()
