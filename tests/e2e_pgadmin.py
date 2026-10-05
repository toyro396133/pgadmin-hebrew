#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

EXPECTED_HE = [
    "לוח מחוונים",
    "מאפיינים",
    "סטטיסטיקות",
    "תלויות",
    "אובייקטים תלויים",
    "תהליכים",
    "סייר האובייקטים",
    "ברוכים הבאים",
]


def is_pgadmin_http_url(url: str) -> bool:
    return url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")


def page_snapshot(browser) -> list[dict]:
    snapshot = []
    for ci, context in enumerate(browser.contexts):
        for pi, page in enumerate(context.pages):
            try:
                snapshot.append(
                    {
                        "context": ci,
                        "page": pi,
                        "url": page.url,
                        "closed": page.is_closed(),
                    }
                )
            except PlaywrightError as exc:
                snapshot.append(
                    {
                        "context": ci,
                        "page": pi,
                        "url": "<unavailable>",
                        "closed": True,
                        "error": str(exc),
                    }
                )
    return snapshot


def wait_for_stable_pgadmin_page(browser, timeout_ms: int = 90000):
    """Ignore Electron splash targets and wait for the real pgAdmin web target."""
    deadline = time.monotonic() + timeout_ms / 1000
    observed: set[str] = set()
    last_snapshot: list[dict] = []

    while time.monotonic() < deadline:
        last_snapshot = page_snapshot(browser)

        for item in last_snapshot:
            url = item.get("url") or ""
            if url:
                observed.add(url)

        pages = [
            page
            for context in browser.contexts
            for page in context.pages
            if not page.is_closed() and is_pgadmin_http_url(page.url or "")
        ]

        for page in pages:
            try:
                # The real window can navigate once during initial key authentication.
                page.wait_for_selector("body", timeout=1500)
                page.wait_for_function(
                    "() => window.pgAdmin && "
                    "window.pgAdmin.csrf_token && "
                    "window.pgAdmin.csrf_token_header",
                    timeout=2000,
                )
                # One final round-trip proves the target survived startup replacement.
                page.evaluate("() => ({href: location.href, ready: document.readyState})")
                return page, sorted(observed), last_snapshot
            except (PlaywrightTimeoutError, PlaywrightError):
                # splash/main target churn is expected during Electron startup
                continue

        time.sleep(0.25)

    raise RuntimeError(
        "Timed out waiting for stable pgAdmin HTTP page. "
        f"Observed URLs: {sorted(observed)}; last targets: {last_snapshot}"
    )


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
        "diagnostics": {
            "cdp": args.cdp,
            "observed_urls": [],
            "targets": [],
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    page = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(args.cdp)
            page, observed, targets = wait_for_stable_pgadmin_page(browser)
            result["diagnostics"]["observed_urls"] = observed
            result["diagnostics"]["targets"] = targets
            result["diagnostics"]["selected_url"] = page.url

            # Persist Hebrew using pgAdmin's real Preferences API.
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
            except PlaywrightError:
                page.evaluate("document.cookie='PGADMIN_LANGUAGE=he; path=/'")

            # Reload the already-stable main window so Flask/Babel sees the saved
            # desktop preference and the template receives the Hebrew language.
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("body", timeout=60000)
            page.wait_for_function(
                "() => window.pgAdmin && window.pgAdmin.csrf_token",
                timeout=60000,
            )
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
                "required": 5,
                "pass": len(found) >= 5,
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

            def open_more_menu():
                # pgAdmin 9.18 desktop collapses panel actions into the
                # MoreVert toolbar button at narrower window widths.
                candidates = [
                    page.locator('button[data-label="עוד"]'),
                    page.locator('button[data-label="More"]'),
                    page.locator('button[aria-label="עוד"]'),
                    page.locator('button[aria-label="More"]'),
                    page.locator('button[title="עוד"]'),
                    page.locator('button[title="More"]'),
                ]
                for candidate in candidates:
                    if candidate.count() > 0:
                        candidate.first.click(timeout=10000)
                        return

                icon = page.locator('svg[data-testid="MoreVertIcon"]')
                if icon.count() > 0:
                    icon.first.locator("xpath=ancestor::button[1]").click(timeout=10000)
                    return

                raise RuntimeError("Could not locate pgAdmin More toolbar button")

            try:
                open_more_menu()
                page.wait_for_timeout(500)
                menu_shot = shots / "01-more-menu.png"
                page.screenshot(path=str(menu_shot), full_page=True)
                result["screenshots"].append(str(menu_shot))
                result["checks"]["more_menu_opened"] = True

                # Capture visible menu text for remote diagnosis.
                menu_texts = page.locator('[role="menu"], [role="menuitem"]').all_inner_texts()
                result["diagnostics"]["more_menu_texts"] = menu_texts
                menu_items = [
                    t.strip()
                    for t in page.locator('[role="menuitem"]').all_inner_texts()
                    if t.strip()
                ]
                result["checks"]["more_menu_localized"] = (
                    "פתיחה" in menu_items and "Open" not in menu_items
                )
            except Exception as exc:
                result["checks"]["more_menu_opened"] = False
                result["errors"].append(f"More menu: {exc}")

            # Close the More menu after its dedicated screenshot.
            try:
                page.keyboard.press("Escape")
            except PlaywrightError:
                pass

            # Open Preferences through the stable Quick Links control.
            # WelcomeDashboard.jsx gives the Configure pgAdmin icon the
            # permanent id "mnu_preferences" and calls pgAdmin.Preferences.show().
            try:
                pref_icon = page.locator("#mnu_preferences")
                if pref_icon.count() > 0:
                    pref_icon.first.locator("xpath=ancestor::*[self::a or self::button][1]").click(
                        timeout=10000
                    )
                    result["diagnostics"]["preferences_open_method"] = "quick-link"
                else:
                    quick_link = page.get_by_text("הגדרת pgAdmin", exact=True)
                    if quick_link.count() > 0:
                        quick_link.first.click(timeout=10000)
                        result["diagnostics"]["preferences_open_method"] = "quick-link-text"
                    else:
                        # Last-resort runtime call uses the same callback as
                        # the official Quick Links control.
                        opened = page.evaluate(
                            """() => {
                              if (window.pgAdmin?.Preferences?.show) {
                                window.pgAdmin.Preferences.show();
                                return true;
                              }
                              return false;
                            }"""
                        )
                        if not opened:
                            raise RuntimeError("Could not locate or invoke pgAdmin Preferences")
                        result["diagnostics"]["preferences_open_method"] = "pgAdmin.Preferences.show"

                page.wait_for_timeout(2000)
                pref_text = page.locator("body").inner_text(timeout=10000)
                result["checks"]["preferences_hebrew"] = (
                    "העדפות" in pref_text
                    and ("ממשק משתמש" in pref_text or "שפה" in pref_text)
                )

                visual = page.evaluate(
                    """async () => {
                      const pref = document.querySelector(
                        '.PreferencesComponent-preferencesContainer'
                      );
                      const tree = document.querySelector(
                        '.PreferencesComponent-treeContainer'
                      );
                      const treeScroller =
                        document.querySelector(
                          '.PreferencesComponent-treeContainer .PgTree-tree [role="tree"]'
                        ) ||
                        document.querySelector(
                          '.PreferencesComponent-treeContainer .PgTree-tree > div'
                        );
                      const treeNode = document.querySelector(
                        '.PreferencesComponent-treeContainer .PgTree-defaultNode'
                      );
                      const helper = document.querySelector(
                        '.PreferencesComponent-preferencesContainer .MuiFormHelperText-root'
                      );

                      const alertProbe = document.createElement('div');
                      alertProbe.className = 'FormFooter-message';
                      alertProbe.textContent = 'SSL: CERTIFICATE_VERIFY_FAILED';
                      document.body.appendChild(alertProbe);

                      const inputProbe = document.createElement('input');
                      inputProbe.type = 'text';
                      inputProbe.value = '~/.anthropic-api-key';
                      pref?.appendChild(inputProbe);

                      await new Promise((resolve) => requestAnimationFrame(() =>
                        requestAnimationFrame(resolve)
                      ));

                      const p = pref ? getComputedStyle(pref) : null;
                      const t = tree ? getComputedStyle(tree) : null;
                      const ts = treeScroller ? getComputedStyle(treeScroller) : null;
                      const tn = treeNode ? getComputedStyle(treeNode) : null;
                      const h = helper ? getComputedStyle(helper) : null;
                      const alertStyle = getComputedStyle(alertProbe);

                      const data = {
                        borderRightWidth: p ? p.borderRightWidth : null,
                        borderLeftWidth: p ? p.borderLeftWidth : null,
                        treeOverflowX: t ? t.overflowX : null,
                        treeInnerOverflowX: ts ? ts.overflowX : null,
                        treeNodeDirection: tn ? tn.direction : null,
                        helperDirection: h ? h.direction : null,
                        helperTextAlign: h ? h.textAlign : null,
                        alertUnicodeBidi: alertStyle.unicodeBidi,
                        alertDirAttribute: alertProbe.getAttribute('dir'),
                        technicalInputDirAttribute: inputProbe.getAttribute('dir'),
                        pageHasHorizontalOverflow:
                          document.documentElement.scrollWidth >
                          document.documentElement.clientWidth + 1,
                      };
                      alertProbe.remove();
                      inputProbe.remove();
                      return data;
                    }"""
                )
                result["diagnostics"]["preferences_visual"] = visual
                result["checks"]["preferences_visual_rtl"] = {
                    "divider_on_right": visual["borderRightWidth"] not in (None, "0px"),
                    "no_left_divider": visual["borderLeftWidth"] in (None, "0px"),
                    "tree_x_clipped": visual["treeOverflowX"] == "hidden",
                    "tree_inner_x_clipped": visual["treeInnerOverflowX"] == "hidden",
                    "tree_nodes_rtl": visual["treeNodeDirection"] == "rtl",
                    "helper_rtl": visual["helperDirection"] in (None, "rtl"),
                    "alerts_plaintext": visual["alertUnicodeBidi"] == "plaintext",
                    "alerts_auto_direction": visual["alertDirAttribute"] == "auto",
                    "technical_input_auto_direction":
                        visual["technicalInputDirAttribute"] == "auto",
                    "no_page_horizontal_overflow": not visual["pageHasHorizontalOverflow"],
                }

                pref_shot = shots / "02-preferences.png"
                page.screenshot(path=str(pref_shot), full_page=True)
                result["screenshots"].append(str(pref_shot))
            except Exception as exc:
                result["checks"]["preferences_hebrew"] = False
                result["errors"].append(f"Preferences: {exc}")
                if page is not None and not page.is_closed():
                    result["diagnostics"]["failure_body_excerpt"] = (
                        page.locator("body").inner_text(timeout=10000)[:5000]
                    )
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
                result["checks"].get("more_menu_opened", False),
                result["checks"].get("more_menu_localized", False),
                result["checks"].get("preferences_hebrew", False),
                all(
                    result["checks"].get("preferences_visual_rtl", {}).values()
                ),
            ]
            result["status"] = "passed" if all(required) else "failed"
            browser.close()

    except Exception as exc:
        result["errors"].append(repr(exc))
        # Best-effort screenshot if a real page exists at failure time.
        try:
            if page is not None and not page.is_closed():
                err_shot = shots / "99-error.png"
                page.screenshot(path=str(err_shot), full_page=True)
                result["screenshots"].append(str(err_shot))
        except Exception as shot_exc:
            result["errors"].append(f"Failure screenshot: {shot_exc}")

    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
