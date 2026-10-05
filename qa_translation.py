#!/usr/bin/env python3
"""QA checks for pgAdmin Hebrew PO files."""
from pathlib import Path
from babel.messages.pofile import read_po
import re, sys, unicodedata

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name('messages.po')
P_NAMED = re.compile(r'%\([^)]+\)[#0 +\-]?(?:\d+|\*)?(?:\.\d+|\.\*)?[diouxXeEfFgGcrs%]')
P_SIMPLE = re.compile(r'%(?!\()[#0 +\-]?(?:\d+|\*)?(?:\.\d+|\.\*)?[diouxXeEfFgGcrs%]')
BRACES = re.compile(r'(?<!\{)\{(?:\d+|[A-Za-z_][A-Za-z0-9_]*|)\}(?!\})')
JS_TEMPLATE = re.compile(r'\$\{[^{}]+\}')
PERCENT_VARIABLE = re.compile(r'%[A-Z][A-Z0-9_]*%')
HTML_TAG = re.compile(r'</?(?:a|b|strong|br|span|code|div|p|em|i|u)(?:\s[^>]*)?/?>', re.I)
BIDI_CONTROL = re.compile('[\u200E\u200F\u202A-\u202E\u2066-\u2069]')

def ph(s):
    return sorted(P_NAMED.findall(s) + P_SIMPLE.findall(s) + BRACES.findall(s) + JS_TEMPLATE.findall(s) + PERCENT_VARIABLE.findall(s) + HTML_TAG.findall(s))

def values(s):
    if isinstance(s, tuple):
        return [x for x in s if x]
    return [s] if s else []

with path.open('r', encoding='utf-8') as f:
    cat = read_po(f, locale='he')

translated = 0
empty = 0
errors = []
bidi_errors = []
for msg in cat:
    if not msg.id:
        continue
    ids = list(msg.id) if isinstance(msg.id, tuple) else [msg.id]
    outs = values(msg.string)
    if not outs:
        empty += 1
        continue
    translated += 1
    if any(BIDI_CONTROL.search(out) or any(unicodedata.category(ch) == 'Cf' for ch in out) for out in outs):
        bidi_errors.append(msg.id)
    src_tokens = ph(' '.join(ids))
    for out in outs:
        if ph(out) != src_tokens and not isinstance(msg.id, tuple):
            errors.append((msg.id, src_tokens, ph(out)))

print(f'File: {path}')
print(f'Translated entries: {translated}')
print(f'Untranslated entries: {empty}')
print(f'Placeholder/markup mismatches: {len(errors)}')
print(f'Unsafe bidi controls: {len(bidi_errors)}')
if errors or bidi_errors:
    for e in errors[:25]:
        print('ERROR:', e)
    for e in bidi_errors[:25]:
        print('BIDI ERROR:', e)
    raise SystemExit(1)
print('QA: PASS')
