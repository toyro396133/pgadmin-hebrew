#!/usr/bin/env python3
"""Merge reviewed Hebrew translations into pgAdmin's official messages.pot.

Usage:
    python merge_into_template.py path/to/messages.pot [output.po]

Requires Babel (the same toolchain pgAdmin uses).
"""
from pathlib import Path
import json, sys
from babel.messages.pofile import read_po, write_po

ROOT = Path(__file__).resolve().parent
if len(sys.argv) < 2:
    raise SystemExit('Usage: python merge_into_template.py path/to/messages.pot [output.po]')

pot_path = Path(sys.argv[1])
out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'messages.full.po'
translations = json.loads((ROOT / 'translations.json').read_text(encoding='utf-8'))

with pot_path.open('r', encoding='utf-8') as f:
    catalog = read_po(f, locale='he', domain='messages')

# Normalize metadata for the Hebrew catalogue.
catalog.project = 'pgAdmin 4'
catalog.version = '9.18'
catalog.msgid_bugs_address = 'pgadmin-hackers@lists.postgresql.org'

matched = 0
plural_skipped = 0
for message in catalog:
    if not message.id:
        continue
    if isinstance(message.id, tuple):
        # Plural entries need a human-reviewed tuple of translations; do not guess.
        plural_skipped += 1
        continue
    if message.id in translations:
        message.string = translations[message.id]
        matched += 1

out_path.parent.mkdir(parents=True, exist_ok=True)
with out_path.open('wb') as f:
    write_po(f, catalog, width=100, include_previous=False)

print(f'Created: {out_path}')
print(f'Reviewed translations merged: {matched}')
print(f'Plural entries left for review: {plural_skipped}')
print(f'Total upstream messages (including header): {len(catalog)}')
