import json
from pathlib import Path
import unittest

from localization.build_batch import validate_pieces
from localization.full_translate import plan_piece
from localization.fix_chat_selection_feedback import chat_link


class ChatSelectionFeedbackTests(unittest.TestCase):
    def test_link_prefix_is_never_sent_to_translator(self):
        for prefix in ['<Select:IID:', '<Examine:IIDDID:', '<RunCmd:String:']:
            def reject(text):
                self.fail('Protocol sent to translator: ' + text)
            self.assertEqual(plan_piece(prefix, reject), [{'keep':prefix}])

    def test_translated_partial_tag_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_pieces(['<Select:IID:', '>', r'<\\Select>'], ['选择: IID :', '>', r'<\\Select>'])

    def test_channel_message_renders_exact_player_link(self):
        source = [r'\[', r'\] <Select:IID:', '>', r"<\\Select>: '", "'\\n"]
        target = chat_link(source)
        rendered = target[0]+'世界'+target[1]+'0x024400000030C5E0'+target[2]+'Player'+target[3]+'hello'+target[4]
        self.assertIn(r'<Select:IID:0x024400000030C5E0>Player<\\Select>', rendered)
        self.assertNotIn('选择', rendered)

    def test_tell_keeps_name_argument_between_grammar_parts(self):
        source = ['You tell <Select:IID:', '>', r"<\\Select>, '", "'\\n"]
        target = chat_link(source)
        self.assertEqual(target[0], '你对<Select:IID:')
        self.assertEqual(target[2], r"<\\Select>说：'")
        validate_pieces(source,target)

    def test_lost_channel_bracket_is_rejected(self):
        source = ['[', '][', ']: <Select:IID:', '>', r'<\\Select> says, ', '\\n']
        broken = chat_link(source); broken[2] = broken[2][1:]
        with self.assertRaises(ValueError):
            validate_pieces(source,broken)

    def test_character_ui_distinguishes_roles_from_name_characters(self):
        path=Path(__file__).resolve().parents[1]/'localization/character-selection-corrections.json'
        terms=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(terms['Characters'],'角色')
        self.assertEqual(terms['New Character'],'新角色')
        self.assertIn('字符',terms['Your name cannot have that many similar characters in a row.'])
