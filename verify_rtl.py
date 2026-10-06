#!/usr/bin/env python3
"""Offline QA for the Hebrew RTL runtime patch and installer logic."""
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parent
EXPECTED_UPSTREAM_BASE_GIT_SHA = "aa433ffb45a06e115722bb4a34590ad9f6a3d6ba"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def normalized_git_blob_sha(data: bytes) -> str:
    """Match Git's canonical LF checkout content even on Windows CRLF checkouts."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    data = data.replace(b"\r\n", b"\n")
    return git_blob_sha(data)


def load_installer():
    spec = importlib.util.spec_from_file_location("install_hebrew", ROOT / "install_hebrew.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    installer = load_installer()
    fixture = ROOT / "tests" / "base.html.REL-9_18"
    raw = fixture.read_bytes()
    actual_sha = normalized_git_blob_sha(raw)
    assert actual_sha == EXPECTED_UPSTREAM_BASE_GIT_SHA, (
        actual_sha,
        EXPECTED_UPSTREAM_BASE_GIT_SHA,
    )

    original = raw.decode("utf-8-sig").replace("\r\n", "\n")
    patched, changed = installer.patch_base(original)
    assert changed
    assert "PGADMIN_HEBREW_RTL_START" in patched
    assert "dir=\"{{ 'rtl' if pgadmin_language == 'he' else 'ltr' }}\"" in patched
    assert 'html[dir="rtl"] .cm-editor' in patched
    assert 'html[dir="rtl"] .xterm' in patched
    assert 'html[dir="rtl"] .rdg' in patched
    assert 'html[dir="rtl"] .PreferencesComponent-preferencesContainer' in patched
    assert 'border-right: 1px solid !important' in patched
    assert 'overflow-x: hidden !important' in patched
    assert 'html[dir="rtl"] .MuiAlert-message' in patched
    assert 'html[dir="rtl"] .FormFooter-message' in patched
    assert '.PreferencesComponent-treeContainer .PgTree-tree > div' in patched
    assert '.PreferencesComponent-treeContainer .PgTree-tree div' in patched
    assert '::-webkit-scrollbar:horizontal' in patched
    assert '.PreferencesComponent-treeContainer .PgTree-defaultNode' in patched
    assert 'html[dir="rtl"] .file-tree .file-entry' in patched
    assert '.file-entry.depth-2 { padding-right: 16px !important; }' in patched
    assert 'localizeDefaultServerGroup' in patched
    assert '.Form-optionIcon.icon-server_group + span' in patched
    assert 'שרתים' in patched
    assert 'input[type="text"]' in patched
    assert "unicode-bidi: plaintext" in patched
    assert "direction: ltr" in patched
    assert 'input[name="host"]' in patched
    assert 'input[name="db"]' in patched
    assert 'input[name="username"]' in patched
    assert 'input[name="file"]' in patched
    assert 'textarea[name="connection_string"]' in patched
    assert 'html[dir="rtl"] .dock-tab .drag-initiator' in patched
    assert 'html[dir="rtl"] .dock-tab .dock-tab-btn' in patched
    assert 'html[dir="rtl"] .dock-tab .dock-tab-close-btn' in patched
    assert 'margin-left: 8px !important' in patched
    assert 'margin-right: 0 !important' in patched
    assert 'html[dir="rtl"] .dock-fbox .dock-nav' in patched
    assert 'html[dir="rtl"] .dock-fbox .dock-extra-content' in patched
    assert '.dock-extra-content .dock-tab-close-btn' in patched
    assert "PGADMIN_HEBREW_RUNTIME_START" in patched
    assert "replaceMenuOpen" in patched
    assert "decodeTechnicalMessageEntities" in patched
    assert "setAutoDirection" in patched
    assert "[role=\"menuitem\"]" in patched or "[role='menuitem']" in patched
    assert "פתיחה" in patched

    # Jinja syntax must remain valid after the patch.
    Environment().parse(patched)

    # Windows packaged/source checkouts commonly use CRLF. The runtime patch
    # must behave identically regardless of newline convention.
    original_crlf = original.replace("\n", "\r\n")
    patched_crlf, changed_crlf = installer.patch_base(original_crlf)
    assert changed_crlf
    assert "PGADMIN_HEBREW_RTL_START" in patched_crlf
    assert "PGADMIN_HEBREW_RUNTIME_START" in patched_crlf
    assert "\r\n" in patched_crlf
    Environment().parse(patched_crlf)

    # Idempotency: running the patch logic twice must not duplicate anything.
    patched2, changed2 = installer.patch_base(patched)
    assert not changed2
    assert patched2 == patched
    assert patched2.count("PGADMIN_HEBREW_RTL_START") == 1
    assert patched2.count("PGADMIN_HEBREW_RUNTIME_START") == 1

    # Upgrade path: an installed older block must be replaced in-place by the
    # current visual RTL block, and the result must then be idempotent.
    stale = patched.replace(
        "border-right: 1px solid !important;",
        "border-right: 0;",
        1,
    )
    upgraded, upgraded_changed = installer.patch_base(stale)
    assert upgraded_changed
    assert upgraded == patched
    upgraded2, upgraded_changed2 = installer.patch_base(upgraded)
    assert not upgraded_changed2
    assert upgraded2 == patched

    stale_runtime = patched.replace("פתיחה", "OPEN_STALE", 1)
    runtime_upgraded, runtime_changed = installer.patch_base(stale_runtime)
    assert runtime_changed
    assert runtime_upgraded == patched

    # Config registration is idempotent too.
    config = "LANGUAGES = {\n    'en': 'English',\n    'sv': 'Swedish'\n}\n"
    config1, changed = installer.patch_config(config)
    assert changed and "'he': 'Hebrew'," in config1
    config2, changed = installer.patch_config(config1)
    assert not changed and config2 == config1

    # End-to-end installer/restore smoke test in a disposable fake pgAdmin web tree.
    with tempfile.TemporaryDirectory() as td:
        web = Path(td) / "web"
        (web / "pgadmin" / "templates").mkdir(parents=True)
        (web / "pgadmin" / "translations").mkdir(parents=True)
        (web / "config.py").write_text(config, encoding="utf-8")
        (web / "version.py").write_text(
            "APP_RELEASE = 9\nAPP_REVISION = 18\n", encoding="utf-8"
        )
        (web / "pgadmin" / "templates" / "base.html").write_text(
            original, encoding="utf-8"
        )

        installer.install(web, no_rtl=False, force=False)
        installed_base = (
            web / "pgadmin" / "templates" / "base.html"
        ).read_text(encoding="utf-8")
        installed_config = (web / "config.py").read_text(encoding="utf-8")
        assert "PGADMIN_HEBREW_RTL_START" in installed_base
        assert "PGADMIN_HEBREW_RUNTIME_START" in installed_base
        assert "replaceMenuOpen" in installed_base
        assert "'he': 'Hebrew'," in installed_config
        assert (
            web
            / "pgadmin"
            / "translations"
            / "he"
            / "LC_MESSAGES"
            / "messages.mo"
        ).is_file()

        installer.restore(web)
        assert (web / "config.py").read_text(encoding="utf-8") == config
        assert (
            web / "pgadmin" / "templates" / "base.html"
        ).read_text(encoding="utf-8") == original

    print("RTL QA: OK")
    print(f"Upstream base.html normalized git blob: {actual_sha}")
    print("Jinja parse: OK (LF + CRLF)")
    print("Idempotency: OK")
    print("Installed RTL/runtime upgrade: OK")
    print("Install/restore smoke test: OK")


if __name__ == "__main__":
    main()
