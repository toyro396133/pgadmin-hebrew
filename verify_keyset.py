#!/usr/bin/env python3
"""Offline integrity check for the REL-9_18 translation key set.

This does not replace verify_upstream.py, which checks the exact official POT
blob. It verifies that translations.json still contains the same 3,684 msgids
whose aggregate fingerprint was computed from pgAdmin REL-9_18 messages.pot.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
EXPECTED_COUNT = 3684
EXPECTED_SUM = 0x4F68EB208D9EA6A7
EXPECTED_XOR = 0xCD354E21EE24A093
EXPECTED_SUM2 = 0x6FDF40EF9DFA1F15
MASK = (1 << 64) - 1


def fnv1a64(text: str) -> int:
    h = 14695981039346656037
    for ch in text:
        h ^= ord(ch)
        h = (h * 1099511628211) & MASK
    return h


data = json.loads((ROOT / 'translations.json').read_text(encoding='utf-8'))
count = len(data)
sum1 = 0
xor1 = 0
sum2 = 0
for key in data:
    h = fnv1a64(key)
    sum1 = (sum1 + h) & MASK
    xor1 ^= h
    sum2 = (sum2 + ((h * h) & MASK)) & MASK

actual = (count, sum1, xor1, sum2)
expected = (EXPECTED_COUNT, EXPECTED_SUM, EXPECTED_XOR, EXPECTED_SUM2)
print(f'Keys: {count}')
print(f'SUM:  0x{sum1:016x}')
print(f'XOR:  0x{xor1:016x}')
print(f'SUM2: 0x{sum2:016x}')
if actual != expected:
    raise SystemExit('Key-set integrity: FAIL')
print('Key-set integrity: PASS (REL-9_18 fingerprint)')
