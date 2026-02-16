#!/usr/bin/env python
"""Compile .po files to .mo format using polib library"""

import polib
from pathlib import Path

def compile_po_with_polib(po_path, mo_path):
    """Compile .po to .mo using polib"""
    try:
        po = polib.pofile(str(po_path))
        po.save_as_mofile(str(mo_path))
        return True
    except Exception as e:
        print(f"Error with polib: {e}")
        return False

if __name__ == '__main__':
    # Compile all language files
    locales = ['en', 'es', 'ht']
    base_dir = Path(__file__).parent
    
    for locale in locales:
        po_path = base_dir / 'locale' / locale / 'LC_MESSAGES' / 'django.po'
        mo_path = base_dir / 'locale' / locale / 'LC_MESSAGES' / 'django.mo'
        
        if po_path.exists():
            print(f'Compiling {po_path}...')
            
            # Delete existing .mo file
            if mo_path.exists():
                mo_path.unlink()
            
            # Compile with polib
            if compile_po_with_polib(po_path, mo_path):
                size = mo_path.stat().st_size
                print(f'✓ Compiled to {mo_path} ({size} bytes)')
            else:
                print(f'✗ Failed to compile {po_path}')
        else:
            print(f'✗ {po_path} not found')
    
    print('Compilation complete!')
