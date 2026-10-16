import unittest
from localization.full_translate import ATOM,cut_text,bad_decoder_token,normalize_input,dumps
from localization.full_build import reconstruct
from localization.sentence_refine import split_sentences


class FullLocalizationTests(unittest.TestCase):
    def test_token_filter_never_suppresses_end_of_sentence(self):
        self.assertFalse(bad_decoder_token('</s>'))
        self.assertTrue(bad_decoder_token('\ue6d5'))
        self.assertTrue(bad_decoder_token('{'))
        self.assertFalse(bad_decoder_token('▁你好'))

    def test_every_source_character_survives_segmentation(self):
        for source in ['A sentence. '*500,'x'*1200,'word '*400,'\n\nHello\n']:
            self.assertEqual(''.join(cut_text(source)),source)
            self.assertTrue(all(len(p)<=300 for p in cut_text(source)))

    def test_protocol_atoms_preserve_dynamic_grammar_and_numbers(self):
        source='<rgb=#00ff00>#1:{item[1]|items[!b]}\\n25% https://example.com?q=x /hail V2 #-1:'
        atoms=[m[0] for m in ATOM.finditer(source)]
        for expected in ['<rgb=#00ff00>','#1:','{','[1]','|','[!b]','}','\\n','25%','https://example.com?q=x','/hail','2','#-1:']:
            self.assertIn(expected,atoms)

    def test_reconstruction_rejects_missing_text_or_unfinished_translation(self):
        templates={dumps('Hello!'):[{'segment':1},{'keep':'!'}]}
        self.assertEqual(reconstruct('Hello!',templates,{1:('Hello','你好','machine_draft','')}),('你好!',set()))
        with self.assertRaisesRegex(ValueError,'lossless'):
            reconstruct('Hello!',templates,{1:('Hell','你好','machine_draft','')})
        with self.assertRaisesRegex(ValueError,'Unfinished'):
            reconstruct('Hello!',templates,{1:('Hello',None,'pending','')})

    def test_accent_normalization_only_changes_model_input(self):
        source='Zímarp and Zâgsha'
        self.assertEqual(normalize_input(source),'Zimarp and Zagsha')
        self.assertEqual(source,'Zímarp and Zâgsha')

    def test_sentence_pass_preserves_every_source_character(self):
        for source in ["'What? Of course! I knew it.'",'I... I know.  Yes!\nNext sentence.', 'One sentence']:
            self.assertEqual(''.join(split_sentences(source)),source)

    def test_double_escaped_protocol_is_one_protected_atom(self):
        self.assertEqual([m[0] for m in ATOM.finditer(r'hello\\qworld\\n')],[r'\\q',r'\\n'])


if __name__=='__main__':unittest.main()
