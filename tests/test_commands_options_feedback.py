import json
from pathlib import Path
import unittest

from localization.build_batch import command_fragment, validate_fragment
from localization.full_translate import technical
from localization.fix_commands_options_feedback import UI_SCOPES


class CommandsOptionsFeedbackTests(unittest.TestCase):
    def test_executable_aliases_and_arguments_are_protected(self):
        for token in ('plugins', 'refresh', 'load', 'unload', 'userchat1,uc1,1', 'on', 'off', 'true', 'false'):
            self.assertTrue(command_fragment(0x250001ab, [token]))
            self.assertTrue(technical([token], 0x250001ab))
            validate_fragment(0x250001ab, [token], [token])
            with self.assertRaisesRegex(ValueError, 'Executable command'):
                validate_fragment(0x250001ab, [token], ['错误译文'])

    def test_visible_labels_and_help_remain_translatable(self):
        validate_fragment(0x250001ff, ['Refresh'], ['刷新'])
        self.assertFalse(command_fragment(0x250001ab, ['Refresh the list of plugins.']))
        self.assertFalse(command_fragment(0x250001ab, ['Plugin ', ' loaded.']))

    def test_reviewed_ui_terms_match_screenshot_context(self):
        terms = json.loads((Path(__file__).resolve().parents[1] / 'localization/options-feedback-corrections.json').read_text(encoding='utf-8'))
        self.assertEqual(terms['graphics']['Scenery'], '景物')
        self.assertEqual(terms['graphics']['Very High'], '极高')
        self.assertEqual(terms['chat']['IMs'], '即时消息')
        self.assertEqual(terms['chat']['LFF'], '组队')
        self.assertEqual(UI_SCOPES[0x25012805], 'chat_channels')
        self.assertEqual(terms['chat_channels']['LFF'], '组队')
        self.assertEqual(terms['chat_channels']['RP'], '角色扮演')
        self.assertEqual(terms['chat_channels']['Emote'], '表情动作')
