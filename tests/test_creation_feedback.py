import json
from pathlib import Path
import unittest

from localization.build_batch import validate_pieces
from localization.fix_creation_feedback import description


class CreationFeedbackTests(unittest.TestCase):
    def test_description_keeps_exact_markup_and_newlines(self):
        source = r'\n<li><rgb=#FFFF00>Class Difficulty:</rgb> Advanced</li>\n\n<li><rgb=#FFFF00>Role:</rgb> Support</li>\n\n<li><rgb=#FFFF00>Gameplay:</rgb> English gameplay.</li>\n\n<li><rgb=#FFFF00>Lore:</rgb> English lore.\n\nEnglish inspiration.</li> '
        edit = {'difficulty': '进阶', 'role': '辅助', 'gameplay': '玩法正文。',
                'lore': '背景正文。', 'inspiration': '职业灵感。'}
        target = description(source, edit)
        validate_pieces([source], [target])
        self.assertIn(r'<rgb=#FFFF00>职业难度：</rgb> 进阶', target)
        self.assertIn(r'背景正文。\n\n职业灵感。</li>', target)

    def test_unexpected_description_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            description('New format', {})

    def test_translated_engine_token_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_pieces(['{{keepspaces}}'], ['{{保留空间}}'])

    def test_all_twelve_classes_have_complete_reviewed_edits(self):
        data = json.loads((Path(__file__).resolve().parents[1] / 'localization/creation-corrections.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data['class_descriptions']), 12)
        for edit in data['class_descriptions'].values():
            self.assertEqual(set(edit), {'difficulty', 'role', 'gameplay', 'lore', 'inspiration'})
            self.assertTrue(all(edit.values()))
