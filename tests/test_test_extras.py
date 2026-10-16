import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import test_extras as tool


class ExtrasTests(unittest.TestCase):
    def fixture(self,temp):
        base=Path(temp);package=base/'package';game=base/'game';plugins=base/'plugins'
        (package/'extras').mkdir(parents=True);(game/'x64').mkdir(parents=True)
        (game/'x64/lotroclient64.exe').write_bytes(b'original')
        rows=[]
        for i,(root,name,before) in enumerate([('game','x64/lotroclient64.exe',b'original'),('plugins','LotroZhItemEnglish.plugin',None)]):
            raw=b'new'+bytes([i]);file=package/'extras'/str(i);file.write_bytes(raw)
            rows.append({'root':root,'target':name,'candidate':'extras/'+str(i),'sha256':hashlib.sha256(raw).hexdigest(),
                         'before_sha256':hashlib.sha256(before).hexdigest() if before else None})
        (package/'extras-plan.json').write_text(json.dumps({'authorized_for_this_test':True,'files':rows}),encoding='utf-8')
        return package,game,plugins

    def test_installs_backs_up_and_restores_only_named_files(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(tool,'require_closed'):
            package,game,plugins=self.fixture(temp);self.assertEqual(tool.install(package,game,plugins),2)
            self.assertEqual((game/'x64/lotroclient64.exe').read_bytes(),b'new\x00')
            tool.restore(package)
            self.assertEqual((game/'x64/lotroclient64.exe').read_bytes(),b'original')
            self.assertFalse((plugins/'LotroZhItemEnglish.plugin').exists())

    def test_second_extra_failure_rolls_back_client(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(tool,'require_closed'):
            package,game,plugins=self.fixture(temp);real_replace=tool.os.replace
            def fail(source,target):
                if Path(target).name=='LotroZhItemEnglish.plugin':raise PermissionError('Injected failure')
                real_replace(source,target)
            with patch.object(tool.os,'replace',side_effect=fail),self.assertRaises(PermissionError):tool.install(package,game,plugins)
            self.assertEqual((game/'x64/lotroclient64.exe').read_bytes(),b'original')
            self.assertFalse((plugins/'LotroZhItemEnglish.plugin').exists())

    def test_unexpected_existing_plugin_stops_before_changes(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(tool,'require_closed'):
            package,game,plugins=self.fixture(temp);plugins.mkdir();(plugins/'LotroZhItemEnglish.plugin').write_bytes(b'existing user file')
            with self.assertRaises(ValueError):tool.install(package,game,plugins)
            self.assertEqual((game/'x64/lotroclient64.exe').read_bytes(),b'original')

    def test_other_plugin_or_path_escape_is_rejected(self):
        for name in ['Other.plugin','../outside.lua']:
            with self.assertRaises(ValueError):tool.target_for({'root':'plugins','target':name},Path('game'),Path('plugins'))

    def test_author_descriptor_is_allowed_without_broadening_other_targets(self):
        target=tool.target_for({'root':'plugins','target':'LotroZh/LotroZhItemEnglish.plugin'},Path('game'),Path('plugins'))
        self.assertEqual(target,Path('plugins/LotroZh/LotroZhItemEnglish.plugin').resolve())
        with self.assertRaises(ValueError):
            tool.target_for({'root':'plugins','target':'LotroZh/Other.plugin'},Path('game'),Path('plugins'))
