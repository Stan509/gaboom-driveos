import polib

try:
    po = polib.mofile('locale/en/LC_MESSAGES/django.mo')
    print(f'✓ .mo file is valid, contains {len(po)} entries')
    # Test a few entries
    for entry in list(po)[:5]:
        print(f'  "{entry.msgid}" -> "{entry.msgstr}"')
except Exception as e:
    print(f'✗ Error reading .mo file: {e}')
