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


def main():
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
            pages = [pg for c in browser.contexts for pg in c.pages]
            if not pages:
                raise RuntimeError("No pgAdmin page found through CDP")

            page = max(pages, key=lambda x: len(x.url or ""))
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            page.wait_for_selector("body", timeout=60000)

            # Persist Hebrew using pgAdmin's real Preferences API.
            page.wait_for_function(
                "() => window.pgAdmin && window.pgAdmin.csrf_token && window.pgAdmin.csrf_token_header",
                timeout=60000,
            )
            pref_result = page.evaluate(
                """async () => {
                  const path = window.location.pathname || '/';
                  const browserPos = path.indexOf('/browser');
                  const prefix = browserPos >= 0 ? path.slice(0, browserPos) : '';
                  const endpoint = prefix + '/preferences/update';
                  const form = new URLSearchParams();
                  form.set('pref_data', JSON.stringify([
                    {name: 'user_language', value: 'he', module: 'misc'}
                  ]));
                  try {
                    const resp = await fetch(endpoint, {
                      method: 'PUT',
                      credentials: 'same-origin',
                      headers: {
                        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                        [window.pgAdmin.csrf_token_header]: window.pgAdmin.csrf_token,
                      },
                      body: form.toString(),
                    });
                    return {
                      ok: resp.ok,
                      status: resp.status,
                      endpoint,
                      text: (await resp.text()).slice(0, 500),
                    };
                  } catch (e) {
                    return {ok: false, status: 0, endpoint, text: String(e)};
                  }
                }"""
            )
            result["checks"]["language_preference_api"] = pref_result
            if not pref_result.get("ok"):
                result["errors"].append(
                    "Preferences API failed: "
                    f"{pref_result.get('status')} {pref_result.get('text')}"
                )

            parts = urlsplit(page.url)
            origin = f"{parts.scheme}://{parts.netloc}"
            try:
                page.context.add_cookies(
                    [{"name": "PGADMIN_LANGUAGE", "value": "he", "url": origin}]
                )
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
            found = [x for x in EXPECTED_HE if x in body_text]
            result["checks"]["hebrew_ui_markers"] = {
                "found": found,
                "required": 3,
                "pass": len(found) >= 3,
            }

            tech = page.evaluate(
                """() => {
                  const test=(cls,tag='div',type=null)=>{
                    const e=document.createElement(tag);
                    if(cls)e.className=cls;
                    if(type)e.type=type;
                    document.body.appendChild(e);
                    const d=getComputedStyle(e).direction;
                    e.remove();
                    return d;
                  };
                  return {
                    codemirror:test('cm-editor'),
                    xterm:test('xterm'),
                    grid:test('rdg'),
                    numberInput:test('', 'input', 'number')
                  };
                }"""
            )
            result["checks"]["technical_ltr"] = {
                k: (v == "ltr") for k, v in tech.items()
            }

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
            except Exception as e:
                result["checks"]["file_menu_hebrew"] = False
                result["errors"].append(f"File menu: {e}")
            page.keyboard.press("Escape")

            try:
                page.get_by_text("קובץ", exact=True).first.click(timeout=10000)
                page.get_by_text("העדפות", exact=True).first.click(timeout=10000)
                page.wait_for_timeout(2000)
                pref_text = page.locator("body").inner_text(timeout=10000)
                result["checks"]["preferences_hebrew"] = (
                    "העדפות" in pref_text
                    and ("ממשק משתמש" in pref_text or "שפה" in pref_text)
                )
                pref_shot = shots / "02-preferences.png"
                page.screenshot(path=str(pref_shot), full_page=True)
                result["screenshots"].append(str(pref_shot))
            except Exception as e:
                result["checks"]["preferences_hebrew"] = False
                result["errors"].append(f"Preferences: {e}")
                err_shot = shots / "99-error.png"
                page.screenshot(path=str(err_shot), full_page=True)
                result["screenshots"].append(str(err_shot))

            required = [
                bool(result["checks"]["language_preference_api"].get("ok")),
                result["checks"]["html_lang_he"],
                result["checks"]["html_dir_rtl"],
                result["checks"]["body_direction_rtl"],
                result["checks"]["hebrew_ui_markers"]["pass"],
                all(result["checks"]["technical_ltr"].values()),
                result["checks"].get("file_menu_hebrew", False),
                result["checks"].get("preferences_hebrew", False),
            ]
            result["status"] = "passed" if all(required) else "failed"
            browser.close()

    except Exception as e:
        result["errors"].append(repr(e))

    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
