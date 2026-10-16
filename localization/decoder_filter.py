"""Build a separate inference model with invalid output-token logits disabled.

Original model weights are retained. This is equivalent to single-token
suppression at decoding, but avoids scanning hundreds of rules at every step.
"""
import hashlib
import json
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent))
sys.path.insert(0,str(BASE/'vendor'))
from localization.full_translate import bad_decoder_token
from ctranslate2.converters.opus_mt import OpusMTConverter
from ctranslate2.converters.marian import load_vocab


class FilteredConverter(OpusMTConverter):
    def _load(self):
        spec=super()._load()
        vocabulary=load_vocab(self._vocab_paths[-1])
        bad=[i for i,t in enumerate(vocabulary) if bad_decoder_token(t)]
        bias=spec.decoder.projection.bias.copy()
        for i in bad:bias.reshape(-1)[i]=-10000
        spec.decoder.projection.bias=bias
        self.filtered=[{'id':i,'token':vocabulary[i]} for i in bad]
        return spec


def build():
    root=BASE/'models/opus-en-zh'
    dest=root/'ct2-int8-filtered'
    converter=FilteredConverter(str(root/'original'))
    converter.convert(str(dest),quantization='int8',force=True)
    report={'method':'output projection bias -10000 for invalid single-token outputs',
            'special_end_token_preserved':True,'filtered_tokens':converter.filtered,
            'model_sha256':hashlib.sha256((dest/'model.bin').read_bytes()).hexdigest()}
    (dest/'filter-manifest.json').write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding='utf-8')
    print('Filtered model created:',len(converter.filtered),'tokens',flush=True)


if __name__=='__main__':build()
