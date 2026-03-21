from __future__ import annotations

import argparse
import ast
from pathlib import Path


def _literal_eval_po_string(token: str) -> str:
    """Parse a PO string literal token, e.g. '"Hello"' -> 'Hello'."""

    token = token.strip()
    if not token:
        return ""
    return ast.literal_eval(token)


def _split_entries(lines: list[str]) -> list[list[str]]:
    entries: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if line.strip() == "":
            if cur:
                entries.append(cur)
                cur = []
            continue
        cur.append(line)
    if cur:
        entries.append(cur)
    return entries


def _extract_key(entry_lines: list[str]) -> tuple[str | None, str | None, str | None]:
    """Extract (msgctxt, msgid, msgid_plural) as *decoded* strings.

    Returns (None, None, None) if entry doesn't look like a standard PO entry.
    """

    msgctxt: str | None = None
    msgid: str | None = None
    msgid_plural: str | None = None
    state: str | None = None

    for raw in entry_lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue

        if s.startswith("msgctxt "):
            msgctxt = _literal_eval_po_string(s[len("msgctxt ") :])
            state = "msgctxt"
            continue

        if s.startswith("msgid_plural "):
            msgid_plural = _literal_eval_po_string(s[len("msgid_plural ") :])
            state = "msgid_plural"
            continue

        if s.startswith("msgid "):
            msgid = _literal_eval_po_string(s[len("msgid ") :])
            state = "msgid"
            continue

        if s.startswith("msgstr"):
            state = "msgstr"
            continue

        if s.startswith('"'):
            part = _literal_eval_po_string(s)
            if state == "msgctxt" and msgctxt is not None:
                msgctxt += part
            elif state == "msgid" and msgid is not None:
                msgid += part
            elif state == "msgid_plural" and msgid_plural is not None:
                msgid_plural += part
            continue

    if msgid is None:
        return (None, None, None)
    return (msgctxt, msgid, msgid_plural)


def dedupe_po(path: Path, *, keep: str = "first") -> tuple[int, int, int]:
    """Remove duplicate PO entries (same msgctxt+msgid+msgid_plural).

    - keep='first' keeps first occurrence (recommended)
    - keep='last' keeps last occurrence
    """

    text = path.read_text(encoding="utf-8")
    entries = _split_entries(text.splitlines())

    seen: dict[tuple[str | None, str, str | None], int] = {}
    kept_entries: list[list[str]] = []
    skipped = 0

    for e in entries:
        msgctxt, msgid, msgid_plural = _extract_key(e)

        # Non-standard block: keep
        if msgid is None:
            kept_entries.append(e)
            continue

        # Header: msgid == ""
        if msgid == "":
            key = ("__header__", "", None)
        else:
            key = (msgctxt, msgid, msgid_plural)

        if key in seen:
            skipped += 1
            if keep == "last":
                kept_entries[seen[key]] = e
            continue

        seen[key] = len(kept_entries)
        kept_entries.append(e)

    out = "\n\n".join("\n".join(e).rstrip("\n") for e in kept_entries).rstrip("\n") + "\n"
    path.write_text(out, encoding="utf-8")
    return (len(entries), len(kept_entries), skipped)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("po_path", type=Path)
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a .bak copy before rewriting",
    )
    parser.add_argument(
        "--keep",
        choices=["first", "last"],
        default="first",
        help="Which duplicate occurrence to keep",
    )
    args = parser.parse_args()

    path: Path = args.po_path
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    if args.backup:
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            bak.write_bytes(path.read_bytes())

    original, kept, skipped = dedupe_po(path, keep=args.keep)
    print(f"{path}: original={original} kept={kept} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
