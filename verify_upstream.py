#!/usr/bin/env python3
"""Verify translations.json against the official pgAdmin 4 v9.18 POT.

Usage:
    python verify_upstream.py [path/to/messages.pot]

If no POT path is provided, the exact REL-9_18 catalogue is downloaded from
pgAdmin's GitHub repository. The Git blob SHA is checked before comparison.
"""
from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen
import hashlib
import json
import sys
import tempfile

from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parent
URL = "https://raw.githubusercontent.com/pgadmin-org/pgadmin4/REL-9_18/web/pgadmin/messages.pot"
EXPECTED_GIT_BLOB_SHA = "3b48f12d1069a762de5abde8c60ee909b7e4ab87"


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def load_pot() -> tuple[Path, bytes, bool]:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        return path, path.read_bytes(), False
    with urlopen(URL, timeout=30) as response:
        data = response.read()
    tmp = tempfile.NamedTemporaryFile(prefix="pgadmin-v9.18-", suffix=".pot", delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name), data, True


pot_path, pot_bytes, temporary = load_pot()
sha = git_blob_sha(pot_bytes)
if sha != EXPECTED_GIT_BLOB_SHA:
    raise SystemExit(
        f"Unexpected upstream blob SHA: {sha}\n"
        f"Expected: {EXPECTED_GIT_BLOB_SHA}\n"
        "Refusing to compare against a different catalogue."
    )

translations = json.loads((ROOT / "translations.json").read_text(encoding="utf-8"))
with pot_path.open("r", encoding="utf-8") as stream:
    catalog = read_po(stream, locale="he", domain="messages")

upstream: set[str] = set()
plural_entries = []
for message in catalog:
    if not message.id:
        continue
    if isinstance(message.id, tuple):
        plural_entries.append(message.id)
        upstream.add(message.id[0])
    else:
        upstream.add(message.id)

local = set(translations)
missing = sorted(upstream - local)
extra = sorted(local - upstream)

print(f"Official upstream messages: {len(upstream)}")
print(f"Local translation keys:     {len(local)}")
print(f"Plural entries upstream:    {len(plural_entries)}")
print(f"Missing translations:       {len(missing)}")
print(f"Stale/extra local keys:      {len(extra)}")
print(f"Git blob SHA:                {sha}")

if missing:
    print("\nMissing:")
    for item in missing:
        print(" -", repr(item))
if extra:
    print("\nExtra:")
    for item in extra:
        print(" -", repr(item))
if plural_entries:
    print("\nWARNING: upstream contains plural entries; review plural handling explicitly.")

if missing or extra:
    raise SystemExit(1)
print("Upstream coverage: PASS (exact key-set match)")
