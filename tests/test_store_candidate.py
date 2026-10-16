import hashlib
from pathlib import Path
import unittest
from localization.store.build_embedded_candidate import patch,BEFORE,AFTER,EXPECTED_SHA


class StoreCandidateTests(unittest.TestCase):
    def test_unmatched_client_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsupported client version'):patch(b'MZ-unrelated-client')

    def test_local_candidate_changes_only_the_pinned_instruction_and_is_reversible(self):
        original=Path(r'D:\Program Files\StandingStoneGames\The Lord of the Rings Online\x64\lotroclient64.exe')
        if not original.exists():self.skipTest('Matching local game is required')
        raw=original.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA:self.skipTest('Different client version')
        changed,offset=patch(raw)
        self.assertEqual(changed[offset:offset+10],AFTER)
        restored=changed[:offset]+BEFORE+changed[offset+10:]
        self.assertEqual(hashlib.sha256(restored).hexdigest(),EXPECTED_SHA)
