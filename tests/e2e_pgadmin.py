#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

EXPECTED_HE = ["קובץ", "כלים", "עזרה", "סייר האובייקטים", "ברוכים הבאים"]


def set_user_language(page, language: str = "he") -> dict:
    """Persist pgAdmin's own user_language preference through its authenticated API."""
    page.wait_for_function(
        "() => window.pgAdmin && window.pgAdmin.csrf_token_header && window.pgAdmin.csrf_token",
        timeout=30000,
    )
    return page.evaluate(
        """async (language) => {
          const path = window.location.pathname || '/';
          const browserIdx = path.indexOf('/browser');
          const base = browserIdx >= 0 ? path.slice(0, browserIdx) : '';
          const url = `${base}/preferences/`;
          const headers = {'Content-Type': 'application/json'};
          headers[window.pgAdmin.csrf_token_header] = window.pgAdmin.csrf_token;

          const getRes = await fetch(url, {credentials: 'same-origin', headers});
          if (!getRes.ok) throw new Error(`GET ${url} failed: ${getRes.status}`);
          const nodes = await getRes.json();

          let target = null;
          for (const mod of nodes || []) {
            for (const cat of mod.children || []) {
              for (const pref of cat.preferences || []) {
                if (pref.name === 'user_language') {
                  target = {
                    category_id: cat.id,
                    id: pref.id,
                    mid: mod.id,
                    name: pref.name,
                    value: language,
                  };
                }
              }
            }
          }
          if (!target) throw new Error('user_language preference was not found');

          const putRes = await fetch(url, {
            method: 'PUT',
            credentials: 'same-origin',
            headers,
            body: JSON.stringify([target]),
          });
          const body = await putRes.text();
          if (!putRes.ok) throw new Error(`PUT ${url} failed: ${putRes.status} ${body}`);
          return {url, status: putRes.status, target};
        }""",
        language,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", default="http://127.0.0.1:9222")
    ap.add_argument("--screenshots", default="artifacts/screenshots")
    ap.add_argument("--report", default="artifacts/e2e-report.json")
    args = ap.parse_args()

    shots = Path(args.screenshots)
    shots.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "failed",
        "checks": {},
        "screenshots": [],
        "errors": [],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(args.cdp)
            pages = [pg for context in browser.contexts for pg in context.pages]
            candidates = [pg for pg in pages if "/browser" in (pg.url or "")]
            if not candidates:
                candidates = [pg for pg in pages if (pg.url or "").startswith(("http://", "https://"))]
            if not candidates:
                raise RuntimeError("No pgAdmin browser page found through CDP")

            page = candidates[0]
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            page.wait_for_selector("body", timeout=60000)

            pref_result = set_user_language(page, "he")
            result["checks"]["language_preference_set"] = {
                "pass": pref_result.get("status") == 200,
                "endpoint": pref_result.get("url"),
            }

            # Keep the cookie aligned too. In desktop mode the saved preference is authoritative.
            parts = urlsplit(page.url)
            origin = f"{parts.scheme}://{parts.netloc}"
            try:
                page.context.add_cookies([
                    {"name": "PGADMIN_LANGUAGE", "value": "he", "url": origin}
                ])
            except Exception:
                page.evaluate("document.cookie='PGADMIN_LANGUAGE=he; path=/'")

            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("body", timeout=60000)
            page.wait_for_timeout(2500)

            lang = page.locator("html").get_attribute("lang")
            direction = page.locator("html").get_attribute("dir")
            body_dir = page.evaluate("getComputedStyle(document.body).direction")
            result["checks"]["html_lang_he"] = lang == "he"
            result["checks"]["html_dir_rtl"] = direction == "rtl"
            result["checks"]["body_direction_rtl"] = body_dir == "rtl"

            body_text = page.locator("body").inner_text(timeout=30000)
            found = [text for text in EXPECTED_HE if text in body_text]
            result["checks"]["hebrew_ui_markers"] = {
                "found": found,
                "required": 3,
                "pass": len(found) >= 3,
            }

            tech = page.evaluate(
                """() => {
                  const test = (cls, tag='div', type=null) => {
                    const e = document.createElement(tag);
                    if (cls) e.className = cls;
                    if (type) e.type = type;
                    document.body.appendChild(e);
                    const d = getComputedStyle(e).direction;
                    e.remove();
                    return d;
                  };
                  return {
                    codemirror: test('cm-editor'),
                    xterm: test('xterm'),
                    grid: test('rdg'),
                    numberInput: test('', 'input', 'number'),
                  };
                }"""
            )
            result["checks"]["technical_ltr"] = {key: value == "ltr" for key, value in tech.items()}

            main_shot = shots / "00-main.png"
            page.screenshot(path=str(main_shot), full_page=True)
            result["screenshots"].append(str(main_shot))

            try:
                page.get_by_text("קובץ", exact=True).first.click(timeout=10000)
                page.wait_for_timeout(500)
                menu_shot = shots / "01-file-menu.png"
                page.screenshot(path=str(menu_shot), full_page=True)
                result["screenshots"].append(str(menu_shot))
                result["checks"]["file_menu_hebrew"] = True
            except Exception as exc:
                result["checks"]["file_menu_hebrew"] = False
                result["errors"].append(f"File menu: {exc}")
            page.keyboard.press("Escape")

            try:
                page.get_by_text("קובץ", exact=True).first.click(timeout=10000)
                page.get_by_text("העדפות", exact=True).first.click(timeout=10000)
                page.wait_for_timeout(2000)
                pref_text = page.locator("body").inner_text(timeout=10000)
                result["checks"]["preferences_hebrew"] = (
                    "העדפות" in pref_text and ("ממשק משתמש" in pref_text or "שפה" in pref_text)
                )
                pref_shot = shots / "02-preferences.png"
                page.screenshot(path=str(pref_shot), full_page=True)
                result["screenshots"].append(str(pref_shot))
            except Exception as exc:
                result["checks"]["preferences_hebrew"] = False
                result["errors"].append(f"Preferences: {exc}")
                err_shot = shots / "99-error.png"
                page.screenshot(path=str(err_shot), full_page=True)
                result["screenshots"].append(str(err_shot))

            required = [
                result["checks"].get("language_preference_set", {}).get("pass", False),
                result["checks"].get("html_lang_he", False),
                result["checks"].get("html_dir_rtl", False),
                result["checks"].get("body_direction_rtl", False),
                result["checks"].get("hebrew_ui_markers", {}).get("pass", False),
                all(result["checks"].get("technical_ltr", {}).values()),
                result["checks"].get("file_menu_hebrew", False),
                result["checks"].get("preferences_hebrew", False),
            ]
            result["status"] = "passed" if all(required) else "failed"
            browser.close()
    except Exception as exc:
        result["errors"].append(repr(exc))

    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())