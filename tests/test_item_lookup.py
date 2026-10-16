import collections
import unittest
from pathlib import Path
import tempfile
from localization.item_lookup.layout import DESCRIPTOR,validate_layout
from localization.item_lookup.build_lookup import add_resource,clean,lua_string,lua_ascii_string,normalize_alias,NAME_ID,PLURAL_ID


class ItemLookupTests(unittest.TestCase):
    def test_plural_alias_maps_to_original_singular_search_name(self):
        index=collections.defaultdict(set)
        add_resource(index,{NAME_ID:(['Huge Pile of Silver Scraps[ps]'],['银渣大堆[ps]']),
                            PLURAL_ID:(['Huge Piles of Silver Scraps[ps]'],['银片大片[ps]'])})
        self.assertEqual(index['银片大片'],{'Huge Pile of Silver Scraps'})

    def test_ambiguous_chinese_name_retains_both_english_options(self):
        index=collections.defaultdict(set)
        for adjective in ['Huge','Massive']:
            add_resource(index,{NAME_ID:([adjective+' Pile of Silver Scraps[ps]'],['银片大片[ps]'])})
        self.assertEqual(len(index['银片大片']),2)

    def test_encoded_grammar_and_dynamic_names_are_not_exported_as_literal_names(self):
        self.assertEqual(clean('<rgb=#FFFFFF>银片</rgb>[ps]'),'银片')
        index=collections.defaultdict(set)
        self.assertEqual(add_resource(index,{NAME_ID:(['Prefix ', ' suffix'],['前缀 ', ' 后缀'])}),0)
        self.assertEqual(add_resource(index,{NAME_ID:(['#1:{Broken|Name}'],['破损'])}),0)

    def test_lua_51_string_literal_preserves_utf8_and_escapes_controls(self):
        self.assertEqual(lua_string('银片"\\\n'),'"银片\\"\\\\\\010"')

    def test_descriptor_in_author_directory_resolves_real_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);descriptor=root/DESCRIPTOR
            descriptor.parent.mkdir(parents=True)
            descriptor.write_bytes((Path(__file__).resolve().parents[1]/'localization/item_lookup/plugin/LotroZhItemEnglish.plugin').read_bytes())
            entry=root/'Plugins/LotroZh/ItemEnglish/Main.lua';entry.parent.mkdir();entry.write_text('-- entry',encoding='utf-8')
            self.assertEqual(validate_layout(root)['entry_file'],'Plugins/LotroZh/ItemEnglish/Main.lua')
            self.assertEqual(validate_layout(root)['version'],'0.1.4')
            entry.unlink()
            with self.assertRaisesRegex(ValueError,'entry file'):validate_layout(root)

    def test_old_root_descriptor_is_rejected_before_lua_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'Plugins').mkdir()
            (root/'Plugins/LotroZhItemEnglish.plugin').write_text('<Plugin/>',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'author directory'):validate_layout(root)

    def test_dictionary_keys_use_exact_utf8_bytes_in_ascii_lua(self):
        value=lua_ascii_string('银碎片的堆积')
        self.assertTrue(value.isascii())
        self.assertTrue(value.startswith('"\\233\\147\\182'))
        self.assertEqual(lua_ascii_string('ABC"\\\n'),'"ABC\\"\\\\\\010"')

    def test_hidden_whitespace_in_aliases_does_not_drop_ambiguous_matches(self):
        index=collections.defaultdict(set)
        add_resource(index,{NAME_ID:(['First Item'],['\ufeff银碎片\u200b的堆积\xa0'])})
        add_resource(index,{NAME_ID:(['Second Item'],['银碎片的堆积'])})
        self.assertEqual(index['银碎片的堆积'],{'First Item','Second Item'})
        self.assertEqual(normalize_alias('甲\u3000 乙'),'甲 乙')
