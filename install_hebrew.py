#!/usr/bin/env python3
"""Install/restore the pgAdmin 4 v9.18 Hebrew localization package.

This script intentionally patches only two small runtime files:
- web/config.py: registers the `he` locale.
- web/pgadmin/templates/base.html: sets semantic RTL direction for Hebrew and
  keeps technical surfaces such as CodeMirror/xterm/data grids LTR.

It also copies messages.po/messages.mo into pgAdmin's translation directory.
Original files are backed up once before modification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

PACKAGE_VERSION = "9.18"
BACKUP_SUFFIX = ".hebrew-9.18.bak"
INSTALL_MANIFEST = ".pgadmin-hebrew-9.18-install.json"
RTL_START = "PGADMIN_HEBREW_RTL_START"
RTL_END = "PGADMIN_HEBREW_RTL_END"

HTML_OLD = '<html lang="{{ request.cookies.get(\'PGADMIN_LANGUAGE\') or \'en\' }}">'
HTML_NEW = (
    "{% set pgadmin_language = request.cookies.get('PGADMIN_LANGUAGE') or 'en' %}\n"
    '<html lang="{{ pgadmin_language }}" '
    'dir="{{ \'rtl\' if pgadmin_language == \'he\' else \'ltr\' }}">'
)

SPINNER_ANCHOR = """        .pg-sp-text {
          font-size: 20px;
          text-align: center;
          color: #fff;
        }
"""

RTL_BLOCK = """
        /* PGADMIN_HEBREW_RTL_START
         * Hebrew is right-to-left, but pgAdmin contains technical surfaces
         * where SQL, terminal output and machine-readable values must remain LTR.
         */
        html[dir="rtl"] body {
          direction: rtl;
          text-align: start;
        }

        html[dir="rtl"] .cm-editor,
        html[dir="rtl"] .cm-editor .cm-scroller,
        html[dir="rtl"] .cm-editor .cm-content,
        html[dir="rtl"] .xterm,
        html[dir="rtl"] .xterm-screen,
        html[dir="rtl"] .xterm-rows,
        html[dir="rtl"] pre,
        html[dir="rtl"] code,
        html[dir="rtl"] kbd,
        html[dir="rtl"] samp {
          direction: ltr;
          text-align: left;
          unicode-bidi: isolate;
        }

        html[dir="rtl"] input[type="number"],
        html[dir="rtl"] input[type="password"],
        html[dir="rtl"] input[type="email"],
        html[dir="rtl"] input[type="url"] {
          direction: ltr;
          text-align: left;
        }

        /* Preserve SQL/data-grid column order. */
        html[dir="rtl"] .rdg {
          direction: ltr;
        }
        html[dir="rtl"] .rdg-cell,
        html[dir="rtl"] .rdg-header-row {
          unicode-bidi: plaintext;
        }
        /* PGADMIN_HEBREW_RTL_END */
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--web-path", type=Path, help="Path to pgAdmin's web directory")
    p.add_argument("--no-rtl", action="store_true", help="Install Hebrew catalog without RTL baseline")
    p.add_argument("--restore", action="store_true", help="Restore files backed up by this installer")
    p.add_argument("--force", action="store_true", help="Allow installation when version.py is not exactly 9.18")
    return p.parse_args()


def candidate_web_paths() -> list[Path]:
    candidates: list[Path] = []
    if os.name == "nt":
        roots = [os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")]
        for root in filter(None, roots):
            rootp = Path(root)
            candidates.extend(rootp.glob("PostgreSQL/*/pgAdmin 4/web"))
            candidates.extend(rootp.glob("pgAdmin 4/v*/web"))
            candidates.extend(rootp.glob("Programs/pgAdmin 4/v*/web"))
            candidates.append(rootp / "pgAdmin 4" / "web")
            candidates.append(rootp / "Programs" / "pgAdmin 4" / "web")
    else:
        candidates += [
            Path("/usr/pgadmin4/web"),
            Path("/usr/lib/pgadmin4/web"),
            Path("/Applications/pgAdmin 4.app/Contents/Resources/web"),
        ]
    # Stable order, existing directories only.
    seen = set()
    out = []
    for p in candidates:
        try:
            rp = p.resolve()
        except OSError:
            continue
        if rp in seen or not rp.is_dir():
            continue
        if (rp / "config.py").is_file() and (rp / "pgadmin" / "templates" / "base.html").is_file():
            seen.add(rp)
            out.append(rp)
    return out


def resolve_web_path(explicit: Path | None) -> Path:
    if explicit:
        p = explicit.expanduser().resolve()
        if not (p / "config.py").is_file():
            raise SystemExit(f"Not a pgAdmin web directory: missing {p / 'config.py'}")
        if not (p / "pgadmin" / "templates" / "base.html").is_file():
            raise SystemExit(f"Not a pgAdmin web directory: missing {p / 'pgadmin/templates/base.html'}")
        return p

    found = candidate_web_paths()
    if len(found) == 1:
        return found[0]
    if not found:
        raise SystemExit("Could not auto-detect pgAdmin's web directory. Pass --web-path explicitly.")
    options = "\n".join(f"  - {p}" for p in found)
    raise SystemExit(f"Multiple pgAdmin installations found. Pass --web-path explicitly:\n{options}")


def detect_version(web: Path) -> str | None:
    version_file = web / "version.py"
    if not version_file.is_file():
        return None
    text = version_file.read_text(encoding="utf-8", errors="replace")
    release = re.search(r"(?m)^APP_RELEASE\s*=\s*(\d+)\s*$", text)
    revision = re.search(r"(?m)^APP_REVISION\s*=\s*(\d+)\s*$", text)
    if release and revision:
        return f"{release.group(1)}.{revision.group(1)}"
    return None


def backup_once(path: Path) -> Path:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def patch_config(text: str) -> tuple[str, bool]:
    if re.search(r"(?m)^\s*'he'\s*:\s*'Hebrew'\s*,?\s*$", text):
        return text, False
    pattern = re.compile(r"(?m)^(\s*'en'\s*:\s*'English'\s*,\s*)$")
    m = pattern.search(text)
    if not m:
        raise ValueError("Could not find the English LANGUAGES entry in config.py")
    indent = re.match(r"\s*", m.group(1)).group(0)
    newline = "\r\n" if "\r\n" in text else "\n"
    replacement = m.group(1) + newline + indent + "'he': 'Hebrew',"
    return text[:m.start()] + replacement + text[m.end():], True


def patch_base(text: str) -> tuple[str, bool]:
    changed = False
    if RTL_START in text:
        # Already patched by this package.
        return text, False

    if HTML_OLD in text:
        text = text.replace(HTML_OLD, HTML_NEW, 1)
        changed = True
    elif "pgadmin_language" not in text or 'dir="{{' not in text:
        raise ValueError("Could not find the expected pgAdmin 9.18 <html lang=...> line in base.html")

    if SPINNER_ANCHOR not in text:
        raise ValueError("Could not find the expected spinner style anchor in base.html")
    text = text.replace(SPINNER_ANCHOR, SPINNER_ANCHOR + RTL_BLOCK, 1)
    return text, True


def write_text_preserving_newlines(path: Path, text: str) -> None:
    # newline='' prevents Python from altering explicit CRLF/LF sequences.
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(text)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def install(web: Path, no_rtl: bool, force: bool) -> None:
    version = detect_version(web)
    if version != PACKAGE_VERSION and not force:
        raise SystemExit(
            f"This package targets pgAdmin {PACKAGE_VERSION}; detected {version or 'unknown'}. "
            "Use --force only after reviewing the patch against your version."
        )

    package = Path(__file__).resolve().parent
    config = web / "config.py"
    base = web / "pgadmin" / "templates" / "base.html"
    target_dir = web / "pgadmin" / "translations" / "he" / "LC_MESSAGES"
    target_po = target_dir / "messages.po"
    target_mo = target_dir / "messages.mo"

    backup_map: dict[str, str | None] = {}

    # Patch config.py.
    config_text = config.read_text(encoding="utf-8", newline="")
    new_config, config_changed = patch_config(config_text)
    if config_changed:
        backup_map[str(config)] = str(backup_once(config))
        write_text_preserving_newlines(config, new_config)

    # Patch base.html for semantic RTL and technical LTR islands.
    if not no_rtl:
        base_text = base.read_text(encoding="utf-8", newline="")
        new_base, base_changed = patch_base(base_text)
        if base_changed:
            backup_map[str(base)] = str(backup_once(base))
            write_text_preserving_newlines(base, new_base)

    # Copy catalogs, backing up any pre-existing files once.
    target_dir.mkdir(parents=True, exist_ok=True)
    for source, target in [(package / "messages.po", target_po), (package / "messages.mo", target_mo)]:
        if not source.is_file():
            raise SystemExit(f"Package file missing: {source}")
        if target.exists():
            backup = target.with_name(target.name + BACKUP_SUFFIX)
            if not backup.exists():
                shutil.copy2(target, backup)
            backup_map[str(target)] = str(backup)
        else:
            backup_map[str(target)] = None
        shutil.copy2(source, target)

    manifest_path = web / INSTALL_MANIFEST
    manifest = {
        "package": "pgAdmin 4 Hebrew localization",
        "target_version": PACKAGE_VERSION,
        "detected_version": version,
        "rtl_enabled": not no_rtl,
        "backups": backup_map,
        "installed": {
            "messages.po": {"path": str(target_po), "sha256": sha256(target_po)},
            "messages.mo": {"path": str(target_mo), "sha256": sha256(target_mo)},
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Installed Hebrew localization into: {web}")
    print(f"pgAdmin version: {version or 'unknown'}")
    print(f"RTL baseline: {'enabled' if not no_rtl else 'disabled'}")
    print("Restart pgAdmin, then select Hebrew in Preferences > User Interface > Language.")


def restore(web: Path) -> None:
    manifest_path = web / INSTALL_MANIFEST
    if not manifest_path.is_file():
        raise SystemExit(f"Install manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    backups = manifest.get("backups", {})
    for target_s, backup_s in backups.items():
        target = Path(target_s)
        if backup_s:
            backup = Path(backup_s)
            if backup.is_file():
                shutil.copy2(backup, target)
                print(f"Restored: {target}")
        else:
            if target.exists():
                target.unlink()
                print(f"Removed installed file: {target}")

    # Restore runtime files even if they weren't recorded as changed during a repeated install.
    already_restored = {Path(t) for t, b in backups.items() if b}
    for target in [web / "config.py", web / "pgadmin" / "templates" / "base.html"]:
        if target in already_restored:
            continue
        backup = target.with_name(target.name + BACKUP_SUFFIX)
        if backup.is_file():
            shutil.copy2(backup, target)
            print(f"Restored: {target}")

    manifest_path.unlink(missing_ok=True)
    print("Hebrew package changes restored. Restart pgAdmin.")


def main() -> None:
    args = parse_args()
    web = resolve_web_path(args.web_path)
    if args.restore:
        restore(web)
    else:
        install(web, args.no_rtl, args.force)


if __name__ == "__main__":
    main()
