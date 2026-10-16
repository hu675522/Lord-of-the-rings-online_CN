import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_full_patch as builder
from tools.audit_window_test_source import CURRENT_ARCHIVES,CACHE_ID,CACHE_HASH


class RuntimeSourceSnapshotTests(unittest.TestCase):
    def fixture(self):
        config={'archives':{name:{'sha256':str(index)*64,'bytes':100+index}
                            for index,name in enumerate(CURRENT_ARCHIVES,1)}}
        old={name:{'original_sha256':r['sha256'],'original_size':r['bytes']} for name,r in config['archives'].items()}
        audit={'kind':'exact-english-runtime-window-test','source_manifest_sha256':'source','map_manifest_sha256':'maps',
            'text_resources_checked':282190,'matching_text_resources':282189,'font_map_source_resources_checked':361,
            'exclude_resource_ids':[CACHE_ID],'all_other_catalog_text_matches':True,'public_resources':311966,
            'changed_text_resources':[{'id':hex(CACHE_ID),'current_sha256':CACHE_HASH,
                'previous_sha256':'6dac59bc95ca58d6c79357f5e79c830e9ae998ddfd7623fb6fa920e52fd74614'}],
            'source_archives':{name:{'previous_sha256':r['sha256'],'original_sha256':CURRENT_ARCHIVES[name],
                                     'original_size':r['bytes']} for name,r in config['archives'].items()}}
        return old,audit

    def invoke(self,audit,old):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'artifacts/audit.json';path.parent.mkdir();path.write_text(json.dumps(audit),encoding='utf-8')
            with patch.object(builder,'ROOT',root):return builder.runtime_source_snapshot(path,old,'source','maps')

    def test_only_exact_snapshot_is_accepted(self):
        old,audit=self.fixture()
        self.assertEqual(self.invoke(audit,old)['exclude_resource_ids'],[CACHE_ID])
        wrong=copy.deepcopy(audit);wrong['source_archives']['client_local_English.dat']['original_sha256']='0'*64
        with self.assertRaises(ValueError):self.invoke(wrong,old)

    def test_stale_manifest_or_missing_coverage_is_rejected(self):
        old,audit=self.fixture()
        for field,value in [('source_manifest_sha256','stale'),('font_map_source_resources_checked',360),('matching_text_resources',0)]:
            wrong=copy.deepcopy(audit);wrong[field]=value
            with self.assertRaises(ValueError):self.invoke(wrong,old)

    def test_unknown_or_additional_resource_exclusions_are_rejected(self):
        old,audit=self.fixture()
        wrong=copy.deepcopy(audit);wrong['exclude_resource_ids'].append(0x250001ab)
        with self.assertRaises(ValueError):self.invoke(wrong,old)
        wrong=copy.deepcopy(audit);wrong['changed_text_resources'][0]['current_sha256']='f'*64
        with self.assertRaises(ValueError):self.invoke(wrong,old)
