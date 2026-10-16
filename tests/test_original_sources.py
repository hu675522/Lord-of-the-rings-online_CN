import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from localization import original_sources


class OriginalSourceTests(unittest.TestCase):
    def setup_config(self,root,backup=False):
        (root/'data').mkdir();game=root/'game';game.mkdir();(game/'client_local_English.dat').write_bytes(b'English')
        info={'game_directory':str(game),'archives':{'client_local_English.dat':{'bytes':7,'sha256':hashlib.sha256(b'English').hexdigest()}}}
        if backup:
            target=root/'test-package/backups';target.mkdir(parents=True)
            (target/'client_local_English.dat.original').write_bytes(b'English');info['source_backup_directory']=str(target)
        (root/'data/original-archives.json').write_text(json.dumps(info),encoding='utf8')
        return game

    def test_restored_game_is_used_before_deployment(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(original_sources,'ROOT',Path(temp)):
            root=Path(temp);game=self.setup_config(root)
            self.assertEqual(original_sources.original_archive('client_local_English.dat'),game/'client_local_English.dat')

    def test_deployed_game_is_never_used_as_original(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(original_sources,'ROOT',Path(temp)):
            root=Path(temp);game=self.setup_config(root,True);(game/'client_local_English.dat').write_bytes(b'Chinese')
            original_sources.verify_sources(['client_local_English.dat'])
            source=original_sources.original_archive('client_local_English.dat');self.assertEqual(source.read_bytes(),b'English')
            source.unlink()
            with self.assertRaises(FileNotFoundError):original_sources.verify_sources(['client_local_English.dat'])

    def test_corrupt_backup_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(original_sources,'ROOT',Path(temp)):
            root=Path(temp);self.setup_config(root,True)
            original_sources.original_archive('client_local_English.dat').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):original_sources.verify_sources(['client_local_English.dat'])


if __name__=='__main__':unittest.main()
