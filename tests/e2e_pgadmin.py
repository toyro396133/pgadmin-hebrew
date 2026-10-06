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

            object_tree = page.evaluate(
                """() => {
                  const icon = document.querySelector(
                    '.file-tree .file-entry .file-icon.icon-server_group'
                  );
                  const row = icon?.closest('.file-entry') || null;
                  const label = row?.querySelector('.file-name') || null;
                  const toggle = row?.querySelector('i.directory-toggle') || null;
                  const rs = row ? getComputedStyle(row) : null;
                  const ts = toggle ? getComputedStyle(toggle, '::before') : null;
                  return {
                    found: Boolean(row),
                    label: label ? label.textContent.trim() : null,
                    rowDirection: rs ? rs.direction : null,
                    rowTextAlign: rs ? rs.textAlign : null,
                    paddingLeft: rs ? rs.paddingLeft : null,
                    paddingRight: rs ? rs.paddingRight : null,
                    toggleTransform: ts ? ts.transform : null,
                  };
                }"""
            )
            result["diagnostics"]["object_explorer_rtl"] = object_tree
            result["checks"]["object_explorer_rtl"] = {
                "server_group_found": bool(object_tree["found"]),
                "default_group_localized": object_tree["label"] != "Servers",
                "row_rtl": object_tree["rowDirection"] == "rtl",
                "row_right_aligned": object_tree["rowTextAlign"] in ("right", "start"),
                "left_padding_cleared": object_tree["paddingLeft"] in ("0px", None),
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
                      alertProbe.textContent = '&lt;urlopen error [SSL: CERTIFICATE_VERIFY_FAILED]&gt;';
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
                        alertText: alertProbe.textContent,
                        technicalInputDirAttribute: inputProbe.getAttribute('dir'),
                        overflowingTreeDescendants: tree
                          ? Array.from(tree.querySelectorAll('*'))
                            .filter((el) => el.scrollWidth > el.clientWidth + 1)
                            .slice(0, 25)
                            .map((el) => {
                              const cs = getComputedStyle(el);
                              return {
                                tag: el.tagName,
                                className: el.className?.toString?.() || '',
                                role: el.getAttribute('role'),
                                clientWidth: el.clientWidth,
                                scrollWidth: el.scrollWidth,
                                overflowX: cs.overflowX,
                                horizontallyScrollable:
                                  ['auto', 'scroll'].includes(cs.overflowX),
                              };
                            })
                          : [],
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
                    "alerts_entities_decoded":
                        visual["alertText"].startswith("<urlopen error"),
                    "technical_input_auto_direction":
                        visual["technicalInputDirAttribute"] == "auto",
                    "tree_has_no_visible_horizontal_scroll":
                        not any(
                            x.get("horizontallyScrollable", False)
                            for x in visual["overflowingTreeDescendants"]
                        ),
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

            # Return to Dashboard before testing object context menus and
            # the non-destructive Register Server dialog.
            try:
                dash_tab = page.get_by_text("לוח מחוונים", exact=True)
                if dash_tab.count() > 0:
                    dash_tab.first.click(timeout=10000)
                    page.wait_for_timeout(800)
            except Exception as exc:
                result["errors"].append(f"Return to Dashboard: {exc}")

            # Object Explorer context menu on the server-group root.
            try:
                server_group_icon = page.locator(
                    '.file-tree .file-entry .file-icon.icon-server_group'
                ).first
                server_group_row = server_group_icon.locator(
                    'xpath=ancestor::div[contains(@class,"file-entry")][1]'
                )
                server_group_row.click(button="right", timeout=10000)
                context_menu = page.locator(
                    'ul[aria-label="Object Context Menu"][data-state="open"]'
                )
                context_menu.wait_for(state="visible", timeout=10000)
                page.wait_for_timeout(400)

                context_items = [
                    t.strip()
                    for t in context_menu.locator(
                        '[role="menuitem"]'
                    ).all_inner_texts()
                    if t.strip()
                ]
                context_visual = context_menu.evaluate(
                    """(menu) => {
                      const cs = getComputedStyle(menu);
                      return {
                        found: true,
                        direction: cs.direction,
                        textAlign: cs.textAlign,
                        ariaLabel: menu.getAttribute('aria-label'),
                        state: menu.getAttribute('data-state'),
                      };
                    }"""
                )
                result["diagnostics"]["server_group_context_menu"] = {
                    "items": context_items,
                    **context_visual,
                }
                hebrew_context_items = sum(
                    1
                    for item in context_items
                    if any("\u0590" <= ch <= "\u05ff" for ch in item)
                )
                result["checks"]["server_group_context_menu_rtl"] = {
                    "menu_found": bool(context_visual["found"]),
                    "menu_rtl": context_visual["direction"] == "rtl",
                    "has_items": len(context_items) > 0,
                    "has_hebrew_items": hebrew_context_items > 0,
                }

                context_shot = shots / "03-object-context-menu.png"
                page.screenshot(path=str(context_shot), full_page=True)
                result["screenshots"].append(str(context_shot))
            except Exception as exc:
                result["checks"]["server_group_context_menu_rtl"] = {
                    "menu_found": False,
                }
                result["errors"].append(f"Server-group context menu: {exc}")
            finally:
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                except PlaywrightError:
                    pass

            # Register Server dialog. Open and inspect only; never submit/save.
            try:
                add_server = page.get_by_text("הוספת שרת חדש", exact=True)
                if add_server.count() == 0:
                    raise RuntimeError("Add New Server quick link was not found")
                add_server.first.click(timeout=10000)

                title = page.get_by_text("רישום - שרת", exact=True)
                if title.count() == 0:
                    title = page.get_by_text("Register - Server", exact=True)
                title.last.wait_for(state="visible", timeout=15000)

                dialog = title.last.locator(
                    'xpath=ancestor::div[contains(@class,"dock-fbox")][1]'
                )
                dialog.wait_for(state="visible", timeout=15000)
                page.wait_for_timeout(1000)

                dialog_text = dialog.inner_text(timeout=10000)
                dialog_visual = dialog.evaluate(
                    """(el) => {
                      const cs = getComputedStyle(el);
                      return {
                        direction: cs.direction,
                        textAlign: cs.textAlign,
                        hasHorizontalOverflow:
                          el.scrollWidth > el.clientWidth + 1,
                      };
                    }"""
                )
                general_markers = ["רישום", "שרת", "כללי", "שם", "חיבור"]
                result["diagnostics"]["register_server_general"] = {
                    "markers_found": [
                        x for x in general_markers if x in dialog_text
                    ],
                    **dialog_visual,
                }
                server_group_display = dialog.locator(
                    ".Form-optionIcon.icon-server_group + span"
                )
                server_group_display_text = (
                    server_group_display.first.inner_text().strip()
                    if server_group_display.count() > 0
                    else None
                )
                result["diagnostics"]["register_server_general"][
                    "server_group_display"
                ] = server_group_display_text
                result["checks"]["register_server_dialog_rtl"] = {
                    "dialog_rtl": dialog_visual["direction"] == "rtl",
                    "hebrew_markers":
                        sum(1 for x in general_markers if x in dialog_text) >= 4,
                    "no_horizontal_overflow":
                        not dialog_visual["hasHorizontalOverflow"],
                    "server_group_display_localized":
                        server_group_display_text in (None, "שרתים"),
                }

                register_general_shot = shots / "04-register-server.png"
                page.screenshot(path=str(register_general_shot), full_page=True)
                result["screenshots"].append(str(register_general_shot))

                connection_tab = dialog.get_by_text("חיבור", exact=True)
                if connection_tab.count() == 0:
                    connection_tab = dialog.get_by_text(
                        "Connection", exact=True
                    )
                if connection_tab.count() == 0:
                    raise RuntimeError("Register Server Connection tab not found")
                connection_tab.last.click(timeout=10000)
                page.wait_for_timeout(800)

                connection_text = dialog.inner_text(timeout=10000)
                connection_markers = [
                    "שם/כתובת מארח",
                    "יציאה",
                    "מסד נתונים לתחזוקה",
                    "שם משתמש",
                    "סיסמה",
                ]
                technical_fields = dialog.evaluate(
                    """(root) => {
                      const wanted = [
                        'host', 'hostaddr', 'port', 'db',
                        'username', 'password', 'service'
                      ];
                      const out = {};
                      for (const name of wanted) {
                        const el = root.querySelector(
                          'input[name="' + name + '"], textarea[name="' + name + '"]'
                        );
                        if (!el) continue;
                        const cs = getComputedStyle(el);
                        out[name] = {
                          direction: cs.direction,
                          textAlign: cs.textAlign,
                          type: el.getAttribute('type'),
                        };
                      }
                      return out;
                    }"""
                )
                result["diagnostics"]["register_server_connection"] = {
                    "markers_found": [
                        x for x in connection_markers if x in connection_text
                    ],
                    "technical_fields": technical_fields,
                }

                required_technical = [
                    name
                    for name in ("host", "port", "db", "username", "password")
                    if name in technical_fields
                ]
                result["checks"]["register_server_connection_form"] = {
                    "hebrew_markers":
                        sum(
                            1 for x in connection_markers
                            if x in connection_text
                        ) >= 4,
                    "technical_fields_found": len(required_technical) >= 3,
                    "technical_fields_ltr":
                        bool(required_technical)
                        and all(
                            technical_fields[name]["direction"] == "ltr"
                            for name in required_technical
                        ),
                }

                register_connection_shot = (
                    shots / "05-register-server-connection.png"
                )
                page.screenshot(
                    path=str(register_connection_shot),
                    full_page=True,
                )
                result["screenshots"].append(
                    str(register_connection_shot)
                )

            except Exception as exc:
                result["checks"].setdefault(
                    "register_server_dialog_rtl",
                    {"dialog_rtl": False},
                )
                result["checks"].setdefault(
                    "register_server_connection_form",
                    {"hebrew_markers": False},
                )
                result["errors"].append(f"Register Server dialog: {exc}")
                try:
                    result["diagnostics"]["register_server_dockboxes"] = [
                        t.strip()
                        for t in page.locator(".dock-fbox").all_inner_texts()
                        if t.strip()
                    ]
                    if page.locator(".dock-fbox").count() > 0:
                        err_shot = shots / "98-register-server-error.png"
                        page.screenshot(path=str(err_shot), full_page=True)
                        result["screenshots"].append(str(err_shot))
                except Exception:
                    pass
            finally:
                # Explicitly close. Never submit/save the server form.
                try:
                    close_btn = page.locator(
                        '.dock-fbox button[data-label="סגירה"], '
                        '.dock-fbox button[data-label="Close"]'
                    )
                    if close_btn.count() > 0 and close_btn.last.is_visible():
                        close_btn.last.click(timeout=5000)
                    else:
                        page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                except Exception:
                    try:
                        page.keyboard.press("Escape")
                    except PlaywrightError:
                        pass

            # Discover existing server capabilities without creating or
            # connecting anything. Connected-only scenarios are reported as
            # available/skipped for the next E2E layer.
            try:
                server_group_icon = page.locator(
                    '.file-tree .file-entry .file-icon.icon-server_group'
                ).first
                server_group_row = server_group_icon.locator(
                    'xpath=ancestor::div[contains(@class,"file-entry")][1]'
                )
                toggle = server_group_row.locator("i.directory-toggle")
                if toggle.count() > 0:
                    classes = toggle.first.get_attribute("class") or ""
                    if "open" not in classes:
                        toggle.first.click(timeout=10000)
                        page.wait_for_timeout(1200)

                server_inventory = page.evaluate(
                    """() => Array.from(
                      document.querySelectorAll('.file-tree .file-entry')
                    ).map((row) => {
                      const icon = row.querySelector(
                        '.file-icon.icon-server, '
                        + '.file-icon.icon-server-not-connected, '
                        + '.file-icon.icon-shared-server-not-connected'
                      );
                      if (!icon) return null;
                      return {
                        label:
                          row.querySelector('.file-name')?.textContent?.trim()
                          || '',
                        iconClass: icon.className,
                        connected:
                          icon.classList.contains('icon-server')
                          && !icon.classList.contains(
                            'icon-server-not-connected'
                          ),
                      };
                    }).filter(Boolean)"""
                )
                result["diagnostics"]["server_inventory"] = server_inventory
                result["checks"]["connected_database_scenarios"] = {
                    "status": (
                        "available"
                        if any(x.get("connected") for x in server_inventory)
                        else "skipped"
                    ),
                    "reason": (
                        None
                        if any(x.get("connected") for x in server_inventory)
                        else "No already-connected server detected; no connection was attempted."
                    ),
                }
            except Exception as exc:
                result["diagnostics"]["server_inventory_error"] = str(exc)
                result["checks"]["connected_database_scenarios"] = {
                    "status": "skipped",
                    "reason": f"Inventory failed without mutating state: {exc}",
                }

            # Inspect an existing server without connecting to it or changing
            # anything: context menu + Properties dialog only.
            server_inventory = result["diagnostics"].get(
                "server_inventory", []
            )
            if server_inventory:
                server_label = server_inventory[0].get("label") or ""
                try:
                    server_name = page.locator(
                        ".file-tree .file-entry .file-name"
                    ).filter(has_text=server_label).first
                    server_row = server_name.locator(
                        'xpath=ancestor::div[contains(@class,"file-entry")][1]'
                    )
                    server_row.click(button="right", timeout=10000)

                    server_menu = page.locator(
                        'ul[aria-label="Object Context Menu"]'
                        '[data-state="open"]'
                    )
                    server_menu.wait_for(state="visible", timeout=10000)
                    server_menu_items = [
                        t.strip()
                        for t in server_menu.locator(
                            '[role="menuitem"]'
                        ).all_inner_texts()
                        if t.strip()
                    ]
                    menu_visual = server_menu.evaluate(
                        """(el) => {
                          const cs = getComputedStyle(el);
                          return {
                            direction: cs.direction,
                            textAlign: cs.textAlign,
                          };
                        }"""
                    )
                    result["diagnostics"]["existing_server_context_menu"] = {
                        "server": server_label,
                        "items": server_menu_items,
                        **menu_visual,
                    }
                    result["checks"]["existing_server_context_menu_rtl"] = {
                        "status": "checked",
                        "menu_rtl": menu_visual["direction"] == "rtl",
                        "has_properties": any(
                            x.startswith("מאפיינים")
                            for x in server_menu_items
                        ),
                        "has_connect_action": any(
                            "חיבור שרת" in x or "Connect Server" in x
                            for x in server_menu_items
                        ),
                    }

                    server_context_shot = (
                        shots / "06-server-context-menu.png"
                    )
                    page.screenshot(
                        path=str(server_context_shot), full_page=True
                    )
                    result["screenshots"].append(
                        str(server_context_shot)
                    )

                    properties_item = server_menu.locator(
                        '[role="menuitem"][data-label="מאפיינים..."], '
                        '[role="menuitem"][data-label="Properties..."]'
                    )
                    if properties_item.count() == 0:
                        raise RuntimeError(
                            "Server Properties context item not found"
                        )
                    properties_item.last.click(timeout=10000)

                    properties_panel = page.locator(".dock-fbox").filter(
                        has_text=server_label
                    ).last
                    properties_panel.wait_for(
                        state="visible", timeout=15000
                    )
                    page.wait_for_timeout(1000)

                    properties_text = properties_panel.inner_text(
                        timeout=10000
                    )
                    properties_visual = properties_panel.evaluate(
                        """(el) => {
                          const cs = getComputedStyle(el);
                          return {
                            direction: cs.direction,
                            textAlign: cs.textAlign,
                            hasHorizontalOverflow:
                              el.scrollWidth > el.clientWidth + 1,
                          };
                        }"""
                    )
                    technical_fields = properties_panel.evaluate(
                        """(root) => {
                          const wanted = [
                            'host', 'hostaddr', 'port', 'db',
                            'username', 'password', 'service'
                          ];
                          const out = {};
                          for (const name of wanted) {
                            const el = root.querySelector(
                              'input[name="' + name + '"], '
                              + 'textarea[name="' + name + '"]'
                            );
                            if (!el) continue;
                            const cs = getComputedStyle(el);
                            out[name] = {
                              direction: cs.direction,
                              textAlign: cs.textAlign,
                            };
                          }
                          return out;
                        }"""
                    )
                    result["diagnostics"]["existing_server_properties"] = {
                        "server": server_label,
                        "markers_found": [
                            x
                            for x in ("כללי", "חיבור", "מתקדם")
                            if x in properties_text
                        ],
                        "technical_fields": technical_fields,
                        **properties_visual,
                    }
                    result["checks"]["existing_server_properties_rtl"] = {
                        "status": "checked",
                        "panel_rtl":
                            properties_visual["direction"] == "rtl",
                        "hebrew_tabs":
                            sum(
                                1
                                for x in ("כללי", "חיבור", "מתקדם")
                                if x in properties_text
                            ) >= 2,
                        "no_horizontal_overflow":
                            not properties_visual[
                                "hasHorizontalOverflow"
                            ],
                        "technical_fields_ltr":
                            bool(technical_fields)
                            and all(
                                data["direction"] == "ltr"
                                for data in technical_fields.values()
                            ),
                    }

                    properties_shot = shots / "07-server-properties.png"
                    page.screenshot(
                        path=str(properties_shot), full_page=True
                    )
                    result["screenshots"].append(str(properties_shot))

                except Exception as exc:
                    result["checks"]["existing_server_context_menu_rtl"] = {
                        "status": "failed",
                        "pass": False,
                    }
                    result["checks"]["existing_server_properties_rtl"] = {
                        "status": "failed",
                        "pass": False,
                    }
                    result["errors"].append(
                        f"Existing server non-destructive audit: {exc}"
                    )
                finally:
                    try:
                        close_btn = page.locator(
                            '.dock-fbox button[data-label="סגירה"], '
                            '.dock-fbox button[data-label="Close"]'
                        )
                        if (
                            close_btn.count() > 0
                            and close_btn.last.is_visible()
                        ):
                            close_btn.last.click(timeout=5000)
                        else:
                            page.keyboard.press("Escape")
                        page.wait_for_timeout(500)
                    except Exception:
                        try:
                            page.keyboard.press("Escape")
                        except PlaywrightError:
                            pass
            else:
                result["checks"]["existing_server_context_menu_rtl"] = {
                    "status": "skipped",
                    "reason": "No existing server is configured.",
                }
                result["checks"]["existing_server_properties_rtl"] = {
                    "status": "skipped",
                    "reason": "No existing server is configured.",
                }

            def optional_check(name):
                data = result["checks"].get(name, {})
                if data.get("status") == "skipped":
                    return True
                return all(
                    bool(value)
                    for key, value in data.items()
                    if key != "status"
                )

            required = [
                bool(result["checks"]["language_preference_api"].get("ok")),
                result["checks"]["html_lang_he"],
                result["checks"]["html_dir_rtl"],
                result["checks"]["body_direction_rtl"],
                result["checks"]["hebrew_ui_markers"]["pass"],
                all(result["checks"]["object_explorer_rtl"].values()),
                all(result["checks"]["technical_ltr"].values()),
                result["checks"].get("more_menu_opened", False),
                result["checks"].get("more_menu_localized", False),
                result["checks"].get("preferences_hebrew", False),
                all(
                    result["checks"].get("preferences_visual_rtl", {}).values()
                ),
                all(
                    result["checks"].get(
                        "server_group_context_menu_rtl", {}
                    ).values()
                ),
                all(
                    result["checks"].get(
                        "register_server_dialog_rtl", {}
                    ).values()
                ),
                all(
                    result["checks"].get(
                        "register_server_connection_form", {}
                    ).values()
                ),
                optional_check("existing_server_context_menu_rtl"),
                optional_check("existing_server_properties_rtl"),
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
