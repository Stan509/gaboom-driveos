#!/usr/bin/env python
"""Compile .po files to .mo format with proper formatting"""

import os
import struct
from pathlib import Path

def compile_po_to_mo(po_path, mo_path):
    """Compile a .po file to .mo format using proper gettext format"""
    translations = {}
    
    # Read .po file
    with open(po_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Parse .po file
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if line.startswith('msgid '):
            # Get msgid
            msgid = line[7:-1]  # Remove 'msgid "' and trailing '"'
            i += 1
            
            # Handle multiline msgid
            while i < len(lines) and lines[i].strip().startswith('"'):
                msgid += lines[i].strip()[1:-1]  # Remove quotes
                i += 1
            
            # Look for msgstr
            if i < len(lines) and lines[i].strip().startswith('msgstr '):
                msgstr = lines[i].strip()[8:-1]  # Remove 'msgstr "' and trailing '"'
                i += 1
                
                # Handle multiline msgstr
                while i < len(lines) and lines[i].strip().startswith('"'):
                    msgstr += lines[i].strip()[1:-1]  # Remove quotes
                    i += 1
                
                # Skip header entry (empty msgid)
                if msgid and msgstr:
                    translations[msgid] = msgstr
            else:
                i += 1
        else:
            i += 1
    
    # Write .mo file in proper gettext format
    keys = sorted(translations.keys())
    
    # Calculate offsets
    keystart = 7 * 4  # Header size
    keyindex = keystart + 16 * len(keys)
    valueindex = keyindex
    for key in keys:
        keyindex += len(key.encode('utf-8')) + 1
    valuestart = keyindex
    
    for key in keys:
        valueindex += len(translations[key].encode('utf-8')) + 1
    
    # Write .mo file
    with open(mo_path, 'wb') as f:
        # Write header
        f.write(struct.pack('<I', 0x950412de))  # Magic number
        f.write(struct.pack('<I', 0))           # Version
        f.write(struct.pack('<I', len(keys)))   # Number of strings
        f.write(struct.pack('<I', keystart))    # Key table offset
        f.write(struct.pack('<I', valuestart))  # Value table offset
        f.write(struct.pack('<I', 0))           # Hash table size
        f.write(struct.pack('<I', 0))           # Hash table offset
        
        # Write key table
        offset = keystart + 16 * len(keys)
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
                # Verify file size
                size = mo_path.stat().st_size
                print(f'  File size: {size} bytes')
            except Exception as e:
                print(f'✗ Error compiling {po_path}: {e}')
                import traceback
                traceback.print_exc()
        else:
            print(f'✗ {po_path} not found')
    
    print('Compilation complete!')
