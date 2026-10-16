"""Validate discovery layout independently of Lua syntax/runtime checks.

Author's working example layout:
https://github.com/shorinji/LotroPluginExamples/tree/master/FredriksExamples
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

DESCRIPTOR = 'Plugins/LotroZh/LotroZhItemEnglish.plugin'


def validate_layout(root):
    root = Path(root).resolve()
    plugins = root / 'Plugins'
    if list(plugins.glob('*.plugin')):
        raise ValueError('Plugin descriptors must be inside the author directory')
    descriptor = root / DESCRIPTOR
    if not descriptor.is_file(): raise ValueError('Missing discoverable plugin descriptor')
    tree = ET.parse(descriptor).getroot()
    if tree.tag != 'Plugin' or tree.findtext('Information/Name') != 'LotroZhItemEnglish':
        raise ValueError('Unexpected plugin identity')
    module = tree.findtext('Package', '')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+', module):
        raise ValueError('Invalid plugin entry module')
    if module.split('.')[0] != descriptor.parent.name:
        raise ValueError('Entry module does not match author directory')
    entry = (plugins / (module.replace('.', '/') + '.lua')).resolve()
    if not entry.is_relative_to(plugins.resolve()) or not entry.is_file():
        raise ValueError('Missing plugin entry file')
    return {'descriptor': DESCRIPTOR, 'entry_module': module,
            'entry_file': entry.relative_to(root).as_posix(),
            'version': tree.findtext('Information/Version')}
