import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from localization.item_lookup import standalone_manager as manager


class StandaloneItemPluginTests(unittest.TestCase):
    def fixture(self,base):
        package=base/'package';plugins=base/'Documents/LOTRO/Plugins';rows=[]
        for name,raw in [('Plugins/LotroZh/LotroZhItemEnglish.plugin',b'descriptor'),
                         ('Plugins/LotroZh/ItemEnglish/Lookup.lua',b'-- lookup')]:
            p=package/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            rows.append({'file':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        (package/'plugin-manifest.json').write_text(json.dumps({'records':rows}),encoding='utf-8')
        game=base/'game';game.mkdir();(game/'client_local_English.dat').write_bytes(b'unchanged game')
        return package,plugins,game

    def test_plugin_install_uninstall_never_changes_dat_or_other_plugins(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(manager,'require_closed'):
            package,plugins,game=self.fixture(Path(temp))
            other=plugins/'Other/Other.plugin';other.parent.mkdir(parents=True);other.write_bytes(b'other')
            self.assertEqual(manager.install(package,plugins),2)
            self.assertEqual((game/'client_local_English.dat').read_bytes(),b'unchanged game')
            self.assertEqual(manager.uninstall(package),2)
            self.assertEqual(other.read_bytes(),b'other')
            self.assertEqual((game/'client_local_English.dat').read_bytes(),b'unchanged game')

    def test_existing_files_and_changed_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(manager,'require_closed'):
            package,plugins,_=self.fixture(Path(temp))
            target=manager.target_for(plugins,'LotroZh/LotroZhItemEnglish.plugin')
            target.parent.mkdir(parents=True);target.write_bytes(b'existing')
            with self.assertRaises(ValueError):manager.install(package,plugins)
            self.assertEqual(target.read_bytes(),b'existing');target.unlink()
            manager.install(package,plugins);target.write_bytes(b'user modified')
            with self.assertRaises(ValueError):manager.uninstall(package)
            self.assertEqual(target.read_bytes(),b'user modified')
            self.assertTrue((plugins/'LotroZh/ItemEnglish/Lookup.lua').exists())

    def test_corrupt_payload_and_game_archive_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(manager,'require_closed'):
            package,plugins,_=self.fixture(Path(temp))
            (package/'Plugins/LotroZh/ItemEnglish/Lookup.lua').write_bytes(b'changed')
            with self.assertRaises(ValueError):manager.install(package,plugins)
            self.assertFalse(plugins.exists())
            for name in ['../escape.lua','client_local_English.dat','LotroZh/ItemEnglish/client_local_English.dat','LotroZh/Other.plugin']:
                with self.assertRaises(ValueError):manager.target_for(plugins,name)

    def test_partial_install_failure_rolls_back_owned_files(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(manager,'require_closed'):
            package,plugins,_=self.fixture(Path(temp));original=Path.replace
            def fail(source,target):
                if Path(target).name=='Lookup.lua':raise PermissionError('injected install failure')
                return original(source,target)
            with patch.object(Path,'replace',new=fail),self.assertRaises(PermissionError):manager.install(package,plugins)
            self.assertFalse((plugins/'LotroZh/LotroZhItemEnglish.plugin').exists())
            self.assertEqual(json.loads((package/'installed-receipt.json').read_text(encoding='utf-8'))['state'],'not-installed')
