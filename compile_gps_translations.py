#!/usr/bin/env python
"""Compile .po → .mo for GPS translations only (Django-free)."""
import os
import struct
import ast
from pathlib import Path

def _compile_po_to_mo(po_path, mo_path):
    data = Path(po_path).read_text(encoding="utf-8").splitlines()
    messages = {}
    msgid = None
    msgstr = None
    state = None
    fuzzy = False

    for line in data:
        line = line.strip()
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith("msgid"):
            if msgid is not None and msgstr is not None and not fuzzy:
                messages[msgid] = msgstr
            # Skip lines like "msgid_plural" by checking exact match
            if not line.startswith("msgid_plural"):
                msgid = ast.literal_eval(line[5:].strip() or '""')
            else:
                msgid = ""
            msgstr = ""
            state = "msgid"
            fuzzy = False
        elif line.startswith("msgid_plural"):
            # Ignore plural forms for this simple compiler
            continue
        elif line.startswith("msgstr"):
            msgstr = ast.literal_eval(line[6:].strip() or '""')
            state = "msgstr"
        elif line.startswith('"'):
            part = ast.literal_eval(line)
            if state == "msgid":
                msgid += part
            elif state == "msgstr":
                msgstr += part
        elif not line:
            if msgid is not None and msgstr is not None and not fuzzy:
                messages[msgid] = msgstr
            msgid = None
            msgstr = None
            state = None
            fuzzy = False

    if msgid is not None and msgstr is not None and not fuzzy:
        messages[msgid] = msgstr

    keys = sorted(messages.keys())
    ids = b"\x00".join(k.encode("utf-8") for k in keys) + b"\x00"
    strs = b"\x00".join(messages[k].encode("utf-8") for k in keys) + b"\x00"

    n = len(keys)
    o1 = 7 * 4
    o2 = o1 + n * 8
    o3 = o2 + n * 8
    ids_start = o3
    strs_start = o3 + len(ids)

    offsets_ids = []
    offset = 0
    for k in keys:
        b = k.encode("utf-8")
        offsets_ids.append((len(b), ids_start + offset))
        offset += len(b) + 1

    offsets_strs = []
    offset = 0
    for k in keys:
        b = messages[k].encode("utf-8")
        offsets_strs.append((len(b), strs_start + offset))
        offset += len(b) + 1

    output = struct.pack("Iiiiiii", 0x950412DE, 0, n, o1, o2, 0, 0)
    for length, off in offsets_ids:
        output += struct.pack("II", length, off)
    for length, off in offsets_strs:
        output += struct.pack("II", length, off)
    output += ids
    output += strs

    Path(mo_path).write_bytes(output)

def main():
    base = Path(__file__).parent / "locale"
    for lang in ("en", "es", "ht"):
        po = base / lang / "LC_MESSAGES" / "django.po"
        mo = base / lang / "LC_MESSAGES" / "django.mo"
        if po.exists():
            _compile_po_to_mo(po, mo)
            print(f"Compiled {lang}: {po} → {mo}")
        else:
            print(f"Missing {po}")

if __name__ == "__main__":
    main()
