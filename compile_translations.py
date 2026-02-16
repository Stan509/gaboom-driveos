#!/usr/bin/env python
"""Compile .po files to .mo format without gettext tools"""

import os
from pathlib import Path
import struct
import re

def compile_po_to_mo(po_path, mo_path):
    """Compile a .po file to .mo format"""
    translations = {}
    
    # Read .po file
    with open(po_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse .po file using regex
    msgid_pattern = re.compile(r'msgid\s+"([^"]*?)"')
    msgstr_pattern = re.compile(r'msgstr\s+"([^"]*?)"')
    
    # Find all msgid/msgstr pairs
    msgids = msgid_pattern.findall(content)
    msgstrs = msgstr_pattern.findall(content)
    
    # Skip the first entry (header)
    for i in range(1, len(msgids)):
        if i < len(msgstrs):
            msgid = msgids[i]
            msgstr = msgstrs[i]
            if msgid and msgstr:
                translations[msgid] = msgstr
    
    # Write .mo file
    keys = sorted(translations.keys())
    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + sum(len(k.encode('utf-8')) + 1 for k in keys)
    
    with open(mo_path, 'wb') as f:
        # Write header
        f.write(struct.pack('<I', 0x950412de))  # Magic number
        f.write(struct.pack('<I', 0))           # Version
        f.write(struct.pack('<I', len(keys)))   # Number of strings
        f.write(struct.pack('<I', 7 * 4))       # Offset of key table
        f.write(struct.pack('<I', keystart))    # Offset of value table
        f.write(struct.pack('<I', 0))           # Hash table size
        f.write(struct.pack('<I', 0))           # Hash table offset
        
        # Write key table
        offset = keystart
        for key in keys:
            k = key.encode('utf-8')
            f.write(struct.pack('<I', len(k)))
            f.write(struct.pack('<I', offset))
            offset += len(k) + 1
        
        # Write value table
        offset = valuestart
        for key in keys:
            value = translations[key].encode('utf-8')
            f.write(struct.pack('<I', len(value)))
            f.write(struct.pack('<I', offset))
            offset += len(value) + 1
        
        # Write keys
        for key in keys:
            k = key.encode('utf-8')
            f.write(k + b'\x00')
        
        # Write values
        for key in keys:
            value = translations[key].encode('utf-8')
            f.write(value + b'\x00')

if __name__ == '__main__':
    # Compile all language files
    locales = ['en', 'es', 'ht']
    base_dir = Path(__file__).parent
    
    for locale in locales:
        po_path = base_dir / 'locale' / locale / 'LC_MESSAGES' / 'django.po'
        mo_path = base_dir / 'locale' / locale / 'LC_MESSAGES' / 'django.mo'
        
        if po_path.exists():
            print(f'Compiling {po_path}...')
            try:
                compile_po_to_mo(po_path, mo_path)
                print(f'✓ Compiled to {mo_path}')
            except Exception as e:
                print(f'✗ Error compiling {po_path}: {e}')
        else:
            print(f'✗ {po_path} not found')
    
    print('Compilation complete!')
