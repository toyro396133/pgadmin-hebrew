#!/usr/bin/env python3
"""Build the reviewed Hebrew pgAdmin catalogue from translations.json.

This creates a compact PO/MO containing reviewed entries only. For a full
upstream-shaped catalogue, use merge_into_template.py with pgAdmin's official
messages.pot for REL-9_18.
"""
from babel.messages.catalog import Catalog
from babel.messages.pofile import write_po
from babel.messages.mofile import write_mo
from datetime import datetime
from pathlib import Path
import json, re

ROOT = Path(__file__).resolve().parent
translations = json.loads((ROOT / 'translations.json').read_text(encoding='utf-8'))

PERCENT_NAMED = re.compile(r'%\([^)]+\)[#0 +\-]?(?:\d+|\*)?(?:\.\d+|\.\*)?[diouxXeEfFgGcrs%]')
PERCENT_SIMPLE = re.compile(r'%(?!\()[#0 +\-]?(?:\d+|\*)?(?:\.\d+|\.\*)?[diouxXeEfFgGcrs%]')
BRACES = re.compile(r'(?<!\{)\{(?:\d+|[A-Za-z_][A-Za-z0-9_]*|)\}(?!\})')
JS_TEMPLATE = re.compile(r'\$\{[^{}]+\}')
PERCENT_VARIABLE = re.compile(r'%[A-Z][A-Z0-9_]*%')
HTML_TAG = re.compile(r'</?(?:a|b|strong|br|span|code|div|p|em|i|u)(?:\s[^>]*)?/?>', re.I)
BIDI_CONTROL = re.compile('[\u200E\u200F\u202A-\u202E\u2066-\u2069]')

def placeholders(s):
    return sorted(PERCENT_NAMED.findall(s) + PERCENT_SIMPLE.findall(s) + BRACES.findall(s) + JS_TEMPLATE.findall(s) + PERCENT_VARIABLE.findall(s) + HTML_TAG.findall(s))

problems = []
for src, dst in translations.items():
    if placeholders(src) != placeholders(dst):
        problems.append((src, placeholders(src), placeholders(dst)))
    if BIDI_CONTROL.search(dst):
        problems.append((src, 'unsafe bidi control', repr(dst)))
if problems:
    raise SystemExit('Placeholder mismatches:\n' + '\n'.join(map(str, problems)))

catalog = Catalog(
    locale='he', domain='messages', project='pgAdmin 4', version='9.18',
    copyright_holder='pgAdmin Development Team',
    msgid_bugs_address='pgadmin-hackers@lists.postgresql.org',
    creation_date=datetime.fromisoformat('2026-09-15T17:11:00+05:30'),
    revision_date=datetime.fromisoformat('2026-10-05T20:13:00+03:00'),
)
catalog.header_comment = '''# Hebrew translations for pgAdmin 4 9.18.\n# Copyright (C) 2026 The pgAdmin Development Team\n# This file is distributed under the same license as pgAdmin 4.\n#\n# Terminology policy: PostgreSQL command names and identifiers remain in their canonical form;\n# UI concepts are translated consistently into Hebrew.\n'''
catalog.fuzzy = False
catalog.last_translator = 'Hebrew Translation Project'
catalog.language_team = 'Hebrew'

for msgid, msgstr in sorted(translations.items(), key=lambda kv: kv[0].casefold()):
    catalog.add(msgid, msgstr)

po_path = ROOT / 'messages.po'
mo_path = ROOT / 'messages.mo'
with po_path.open('wb') as f:
    write_po(f, catalog, width=100, sort_output=False, include_previous=False)
with mo_path.open('wb') as f:
    write_mo(f, catalog)

print(f'Wrote {po_path} with {len(translations)} reviewed translations')
print(f'Wrote {mo_path}')
print('Plural forms:', catalog.plural_forms)
