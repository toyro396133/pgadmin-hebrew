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
RUNTIME_START = "PGADMIN_HEBREW_RUNTIME_START"
RUNTIME_END = "PGADMIN_HEBREW_RUNTIME_END"

HTML_OLD = '<html lang="{{ request.cookies.get(\'PGADMIN_LANGUAGE\') or \'en\' }}">'
HTML_NEW = (
    "{% set pgadmin_language = request.cookies.get('PGADMIN_LANGUAGE') or 'en' %}\n"
    '<html lang="{{ pgadmin_language }}" '
    'dir="{{ \'rtl\' if pgadmin_language == \'he\' else \'ltr\' }}">'
)

RTL_BLOCK = """
        /* PGADMIN_HEBREW_RTL_START
         * Hebrew is right-to-left, but pgAdmin contains technical surfaces
         * where SQL, terminal output and machine-readable values must remain LTR.
         */
        html[dir="rtl"] body {
          direction: rtl;
          text-align: start;
        }

        /* Keep ordinary form chrome and explanatory copy naturally RTL. */
        html[dir="rtl"] .Form-label,
        html[dir="rtl"] .MuiInputLabel-root,
        html[dir="rtl"] .MuiFormHelperText-root,
        html[dir="rtl"] .MuiFormControl-root,
        html[dir="rtl"] .MuiFormControlLabel-root {
          direction: rtl;
          text-align: right;
        }

        html[dir="rtl"] .MuiFormHelperText-root,
        html[dir="rtl"] .MuiAlert-message,
        html[dir="rtl"] [role="alert"],
        html[dir="rtl"] .FormFooter-message,
        html[dir="rtl"] .FormFooter-messageCenter {
          unicode-bidi: plaintext;
        }

        html[dir="rtl"] .FormFooter-message {
          margin-left: 0 !important;
          margin-right: 0.5rem !important;
          text-align: start;
        }

        html[dir="rtl"] .FormFooter-closeButton {
          margin-left: 0 !important;
          margin-right: auto !important;
        }

        html[dir="rtl"] .Form-label [data-testid="Error"] {
          margin-left: 0 !important;
          margin-right: auto !important;
        }

        /* pgAdmin Preferences uses physical left/right rules in its MUI styles.
         * Correct the split-pane divider and keep the Hebrew tree/pane tidy.
         */
        html[dir="rtl"] .PreferencesComponent-header,
        html[dir="rtl"] .PreferencesComponent-body,
        html[dir="rtl"] .PreferencesComponent-bodyWrap,
        html[dir="rtl"] .PreferencesComponent-treeContainer,
        html[dir="rtl"] .PreferencesComponent-preferencesContainer {
          direction: rtl;
        }

        html[dir="rtl"] .PreferencesComponent-searchInput {
          margin-left: 0 !important;
          margin-right: auto !important;
        }

        html[dir="rtl"] .PreferencesComponent-bodyWrap {
          overflow: hidden;
        }

        html[dir="rtl"] .PreferencesComponent-treeContainer {
          overflow-x: hidden !important;
          min-width: 0;
        }

        html[dir="rtl"] .PreferencesComponent-treeContainer .PgTree-tree,
        html[dir="rtl"] .PreferencesComponent-treeContainer .PgTree-tree > div,
        html[dir="rtl"] .PreferencesComponent-treeContainer .PgTree-tree [role="tree"] {
          overflow-x: hidden !important;
          max-width: 100% !important;
        }

        html[dir="rtl"] .PreferencesComponent-treeContainer .PgTree-defaultNode {
          direction: rtl !important;
          text-align: right;
          flex-direction: row;
        }

        html[dir="rtl"] .PreferencesComponent-treeContainer .PgTree-defaultNode > span > svg {
          transform: scaleX(-1);
          transform-origin: center;
        }

        html[dir="rtl"] .PreferencesComponent-treeContainer .PgTree-nodeLabel {
          direction: rtl;
          text-align: right;
        }

        html[dir="rtl"] .PreferencesComponent-treeContainer .PgTree-indentLine {
          margin-left: 0 !important;
          margin-right: -36px !important;
          border-left: 0 !important;
          border-right: 1px solid currentColor;
        }

        html[dir="rtl"] .PreferencesComponent-preferencesContainer {
          border-left: 0 !important;
          border-right: 1px solid !important;
          overflow-x: hidden;
          min-width: 0;
        }

        html[dir="rtl"] .PreferencesComponent-preferencesContainer .MuiGrid-root,
        html[dir="rtl"] .PreferencesComponent-preferencesContainer .MuiFormControl-root,
        html[dir="rtl"] .PreferencesComponent-preferencesContainerBackground {
          min-width: 0;
          max-width: 100%;
        }

        html[dir="rtl"] .PreferencesComponent-noSelection,
        html[dir="rtl"] .PreferencesComponent-preferencesContainer .MuiFormHelperText-root {
          text-align: right;
        }

        html[dir="rtl"] .PreferencesComponent-preferencesContainer input[type="text"],
        html[dir="rtl"] .PreferencesComponent-preferencesContainer textarea {
          unicode-bidi: plaintext;
        }

        /* Mirror the Object Explorer tree itself, not only its containing pane. */
        html[dir="rtl"] .file-tree,
        html[dir="rtl"] .file-tree .file-entry,
        html[dir="rtl"] .file-tree .file-label,
        html[dir="rtl"] .file-tree .file-name {
          direction: rtl !important;
          text-align: right !important;
        }

        html[dir="rtl"] .file-tree .file-entry {
          padding-left: 0 !important;
          padding-right: 2px !important;
        }

        html[dir="rtl"] .file-tree .file-entry.depth-1 { padding-right: 0 !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-2 { padding-right: 16px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-3 { padding-right: 32px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-4 { padding-right: 48px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-5 { padding-right: 64px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-6 { padding-right: 80px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-7 { padding-right: 96px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-8 { padding-right: 112px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-9 { padding-right: 128px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-10 { padding-right: 144px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-11 { padding-right: 160px !important; }
        html[dir="rtl"] .file-tree .file-entry.depth-12 { padding-right: 176px !important; }

        html[dir="rtl"] .file-tree .file-entry > i.directory-toggle:before {
          margin-left: 0 !important;
          margin-right: 5px !important;
          transform: scaleX(-1) !important;
        }

        html[dir="rtl"] .file-tree .file-entry > i.directory-toggle.open:before {
          transform: none !important;
        }

        html[dir="rtl"] .file-tree .file-label {
          margin-left: 0 !important;
          margin-right: 2px !important;
        }

        html[dir="rtl"] .file-tree .file-entry.file .file-label,
        html[dir="rtl"] .file-tree .file-entry.prompt.new .file-label {
          margin-left: 0 !important;
          margin-right: 18px !important;
        }

        html[dir="rtl"] .file-tree .file-entry:before {
          transform: scaleX(-1);
          transform-origin: center;
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
          direction: ltr !important;
          text-align: left !important;
          unicode-bidi: isolate;
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

RUNTIME_SHIM = """
<script type="application/javascript" nonce="{{ csp_nonce }}">
/* PGADMIN_HEBREW_RUNTIME_START */
(function () {
  if (document.documentElement.dir !== 'rtl') return;

  function candidates(root, selector) {
    const out = [];
    if (root && root.nodeType === 1 && root.matches && root.matches(selector)) {
      out.push(root);
    }
    if (root && root.querySelectorAll) {
      out.push(...root.querySelectorAll(selector));
    }
    return out;
  }

  function setAutoDirection(root) {
    const selector = [
      '.FormFooter-message',
      '.FormFooter-messageCenter',
      '.PreferencesComponent-preferencesContainer input[type="text"]',
      '.PreferencesComponent-preferencesContainer textarea'
    ].join(',');
    for (const el of candidates(root, selector)) {
      el.setAttribute('dir', 'auto');
    }
  }

  function replaceMenuOpen(root) {
    for (const el of candidates(root, '[role="menuitem"]')) {
      if ((el.textContent || '').trim() !== 'Open') continue;
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        if ((node.nodeValue || '').trim() === 'Open') {
          node.nodeValue = node.nodeValue.replace('Open', 'פתיחה');
          break;
        }
      }
    }
  }

  function localizeDefaultServerGroup(root) {
    for (const icon of candidates(
      root,
      '.file-tree .file-entry.depth-1 .file-icon.icon-server_group'
    )) {
      const label = icon.parentElement?.querySelector('.file-name');
      if (label && (label.textContent || '').trim() === 'Servers') {
        label.textContent = 'שרתים';
      }
    }
  }

  function apply(root) {
    setAutoDirection(root);
    replaceMenuOpen(root);
    localizeDefaultServerGroup(root);
  }

  function start() {
    apply(document);
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node.nodeType === 1) apply(node);
        }
      }
    });
    observer.observe(document.body, {childList: true, subtree: true});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }
}());
/* PGADMIN_HEBREW_RUNTIME_END */
</script>
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

    if HTML_OLD in text:
        text = text.replace(HTML_OLD, HTML_NEW, 1)
        changed = True
    elif "pgadmin_language" not in text or 'dir="{{' not in text:
        raise ValueError("Could not find the expected pgAdmin 9.18 <html lang=...> line in base.html")

    newline = "\r\n" if "\r\n" in text else "\n"
    rtl_block = RTL_BLOCK.replace("\n", newline)
    runtime_shim = RUNTIME_SHIM.replace("\n", newline)

    # Upgrade an older Hebrew RTL block in place.
    block_re = re.compile(
        r"(?:\r?\n)?[ \t]*/\* " + re.escape(RTL_START) +
        r".*?[ \t]*/\* " + re.escape(RTL_END) + r" \*/(?:\r?\n)?",
        re.DOTALL,
    )
    existing = block_re.search(text)
    if existing:
        if existing.group(0) != rtl_block:
            text = text[:existing.start()] + rtl_block + text[existing.end():]
            changed = True
    else:
        if RTL_START in text or RTL_END in text:
            raise ValueError("Found an incomplete pgAdmin Hebrew RTL block in base.html")

        style_open = text.find('<style nonce="{{ csp_nonce }}">')
        if style_open < 0:
            raise ValueError("Could not find the expected CSP style block in base.html")
        style_close = text.find("</style>", style_open)
        if style_close < 0:
            raise ValueError("Could not find the end of the expected CSP style block in base.html")
        style_segment = text[style_open:style_close]
        if ".pg-sp-text" not in style_segment:
            raise ValueError("Could not find .pg-sp-text in the expected pgAdmin base style block")
        text = text[:style_close] + rtl_block + text[style_close:]
        changed = True

    # Runtime shim handles the few UI fragments that are generated dynamically
    # and cannot be corrected reliably with static CSS/gettext alone.
    runtime_re = re.compile(
        r"(?:\r?\n)?<script[^>]*>[ \t]*\r?\n?/\* " +
        re.escape(RUNTIME_START) +
        r".*?/\* " + re.escape(RUNTIME_END) +
        r" \*/[ \t]*\r?\n?</script>(?:\r?\n)?",
        re.DOTALL,
    )
    existing_runtime = runtime_re.search(text)
    if existing_runtime:
        if existing_runtime.group(0) != runtime_shim:
            text = (
                text[:existing_runtime.start()]
                + runtime_shim
                + text[existing_runtime.end():]
            )
            changed = True
    else:
        if RUNTIME_START in text or RUNTIME_END in text:
            raise ValueError("Found an incomplete pgAdmin Hebrew runtime shim in base.html")

        body_anchor = (
            '<script type="application/javascript" nonce="{{ csp_nonce }}">'
            + newline
            + '            {% block init_script %}{% endblock %}'
            + newline
            + '</script>'
        )
        anchor_pos = text.find(body_anchor)
        if anchor_pos < 0:
            raise ValueError("Could not find the pgAdmin init_script anchor in base.html")
        insert_at = anchor_pos + len(body_anchor)
        text = text[:insert_at] + runtime_shim + text[insert_at:]
        changed = True

    return text, changed


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
