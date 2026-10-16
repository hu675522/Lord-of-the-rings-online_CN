import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.prepare_github_source import prepare
from tools.verify_artifact_files import FORMAT,verify_manifest


class PublicationToolTests(unittest.TestCase):
    def test_verification_reads_nested_font_records_and_does_not_change_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);font=root/'fonts';font.mkdir()
            (font/'glyph.bin').write_bytes(b'font')
            f={'records':[{'file':'glyph.bin','sha256':hashlib.sha256(b'font').hexdigest(),'bytes':4}]}
            raw=json.dumps(f).encode();(font/'manifest.json').write_bytes(raw)
            manifest={'format':FORMAT,'artifacts':{'fonts/manifest.json':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}}}
            path=root/'manifest.json';path.write_text(json.dumps(manifest),encoding='utf8')
            before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=verify_manifest(path)
            self.assertEqual(result['verified_files'],2);self.assertFalse(result['installable'])
            self.assertEqual(before,{p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_modified_file_cannot_pass_hash_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'data.bin').write_bytes(b'bad!')
            manifest={'format':FORMAT,'artifacts':{'data.bin':{'sha256':hashlib.sha256(b'good').hexdigest(),'bytes':4}}}
            path=root/'manifest.json';path.write_text(json.dumps(manifest),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'SHA-256'):verify_manifest(path)

    def test_manifest_cannot_read_outside_asset_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'assets').mkdir();(root/'private').write_bytes(b'private')
            manifest={'format':FORMAT,'artifacts':{'../private':{'sha256':hashlib.sha256(b'private').hexdigest(),'bytes':7}}}
            path=root/'assets/manifest.json';path.write_text(json.dumps(manifest),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'路径'):verify_manifest(path)

    def test_preview_excludes_large_data_and_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'README.md').write_text('public',encoding='utf8')
            (root/'runtime.json').write_text('private',encoding='utf8')
            (root/'localization/full').mkdir(parents=True)
            (root/'localization/full/jobs.sqlite3').write_bytes(b'private translations')
            output=root/'release/preview';report=prepare(root,output)
            self.assertEqual([r['file'] for r in report['files']],['README.md'])
            self.assertFalse((output/'runtime.json').exists())
            self.assertFalse((output/'localization/full').exists())
            with self.assertRaises(FileExistsError):prepare(root,output)
            self.assertEqual((root/'runtime.json').read_text(encoding='utf8'),'private')

    def test_preview_rejects_destination_outside_release_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);target=root/'source-copy'
            with self.assertRaises(ValueError):prepare(root,target)
            self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
