import unittest
from localization.build_batch import validate_pieces, preserve_reason


class FormatPreservationTests(unittest.TestCase):
    def test_product_name_preservation_does_not_skip_visible_action(self):
        self.assertIsNotNone(preserve_reason(['MyLOTRO']))
        self.assertIsNone(preserve_reason(['Toggle MyLOTRO']))

    def test_cannot_remove_dynamic_boundary(self):
        with self.assertRaisesRegex(ValueError,'boundaries'):
            validate_pieces(['Hello ', '!'],['你好！'])

    def test_cannot_drop_color_or_newline(self):
        with self.assertRaisesRegex(ValueError,'control'):
            validate_pieces(['<rgb=#00FF00>Hello</rgb>\\nWorld'],['你好世界'])

    def test_localized_plural_branches_keep_selector(self):
        validate_pieces([' Class Trait {Points|Point[1]}'],[' 职业特性{点数|点数[1]}'])
        with self.assertRaisesRegex(ValueError,'control'):
            validate_pieces(['{Points|Point[1]}'],['{点数|点数[2]}'])

    def test_utf16_limit_counts_surrogate_pair(self):
        with self.assertRaisesRegex(ValueError,'length limit'):
            validate_pieces(['valid'],['😀'*16384])

    def test_cannot_drop_numbered_argument_or_negated_selector(self):
        with self.assertRaisesRegex(ValueError,'control'):
            validate_pieces(['#-1:{Sir[m]|Madam[f]}'],['#1:{先生[m]|女士[f]}'])
        with self.assertRaisesRegex(ValueError,'control'):
            validate_pieces(['#1:{month[!b1]|months[!b]}'],['{月[!b1]|月[!b]}'])
        with self.assertRaisesRegex(ValueError,'control'):
            validate_pieces(['#1:{month[!b1]|months[!b]}'],['#1:{月[b1]|月[b]}'])


if __name__=='__main__':unittest.main()
