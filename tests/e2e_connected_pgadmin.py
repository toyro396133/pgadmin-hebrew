#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from e2e_pgadmin import wait_for_pgadmin_ui_ready, wait_for_stable_pgadmin_page


def first_visible(locator):
    count = locator.count()
    for i in range(count):
        item = locator.nth(i)
        try:
            if item.is_visible():
                return item
        except PlaywrightError:
            pass
    return None


def click_app_menu_item(page, menu_labels, item_labels):
    menu_selector = ", ".join(
        f'button[data-label="{label}"]' for label in menu_labels
    )
    menu = first_visible(page.locator(menu_selector))
    if menu is None:
        raise RuntimeError(
            f"App menu button not found: {', '.join(menu_labels)}"
        )
    menu.click(timeout=10000)

    item_selector = ", ".join(
        f'li[data-label="{label}"]' for label in item_labels
    )
    item = first_visible(page.locator(item_selector))
    if item is None:
        page.keyboard.press("Escape")
        raise RuntimeError(
            f"Menu item not found: {', '.join(item_labels)}"
        )
    item.click(timeout=10000)


def wait_for_query_frame(page, timeout_s=30):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if (
                    frame.locator("#id-query").count() > 0
                    or frame.locator(".cm-editor").count() > 0
                ):
                    return frame
            except PlaywrightError:
                pass
        time.sleep(0.25)
    raise RuntimeError("Query Tool iframe did not become ready")


def close_float_dialog(page):
    close = first_visible(
        page.locator(
            '.dock-fbox button[data-label="סגירה"], '
            '.dock-fbox button[data-label="Close"]'
        )
    )
    if close is not None:
        close.click(timeout=5000)
    else:
        page.keyboard.press("Escape")
    page.wait_for_timeout(500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", required=True)
    ap.add_argument("--screenshots", default="artifacts/screenshots")
    ap.add_argument(
        "--report",
        default="artifacts/connected-e2e-report.json",
    )
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
        "diagnostics": {"cdp": args.cdp},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(args.cdp)
            page, observed, targets = wait_for_stable_pgadmin_page(browser)
            wait_for_pgadmin_ui_ready(page, timeout_ms=90000)
            result["diagnostics"]["observed_urls"] = observed
            result["diagnostics"]["targets"] = targets
            result["diagnostics"]["selected_url"] = page.url

            # Resolve an already-connected server and a connectable database.
            inventory = page.evaluate(
                """async () => {
                  const tree = window.pgAdmin?.Browser?.tree;
                  if (!tree) {
                    throw new Error('pgAdmin Browser tree is unavailable');
                  }

                  for (const group of tree.children() || []) {
                    const gd = tree.itemData(group) || {};
                    if (gd._type !== 'server_group') continue;
                    if (tree.isClosed(group)) await tree.open(group);
                    await tree.ensureLoaded(group);

                    for (const server of tree.children(group) || []) {
                      const sd = tree.itemData(server) || {};
                      if (sd._type !== 'server' || !sd.connected) continue;

                      if (tree.isClosed(server)) await tree.open(server);
                      await tree.ensureLoaded(server);

                      const dbCollection = (tree.children(server) || []).find(
                        (item) =>
                          (tree.itemData(item) || {})._type === 'coll-database'
                      );
                      if (!dbCollection) {
                        return {
                          connectedServer: {
                            label: sd._label ?? sd.label ?? server.fileName ?? '',
                            path: server.path || null,
                          },
                          database: null,
                          reason: 'Database collection not found.',
                        };
                      }

                      if (tree.isClosed(dbCollection)) {
                        await tree.open(dbCollection);
                      }
                      await tree.ensureLoaded(dbCollection);

                      const dbs = (tree.children(dbCollection) || [])
                        .filter(
                          (item) =>
                            (tree.itemData(item) || {})._type === 'database'
                        );

                      const database =
                        dbs.find((item) => {
                          const d = tree.itemData(item) || {};
                          const label =
                            d._label ?? d.label ?? item.fileName ?? '';
                          return label === 'postgres';
                        })
                        || dbs[0]
                        || null;

                      if (!database) {
                        return {
                          connectedServer: {
                            label: sd._label ?? sd.label ?? server.fileName ?? '',
                            path: server.path || null,
                          },
                          database: null,
                          reason: 'No database node was found.',
                        };
                      }

                      const dd = tree.itemData(database) || {};
                      await tree.select(database, true);
                      await new Promise((resolve) =>
                        requestAnimationFrame(() =>
                          requestAnimationFrame(resolve)
                        )
                      );

                      return {
                        connectedServer: {
                          label: sd._label ?? sd.label ?? server.fileName ?? '',
                          path: server.path || null,
                        },
                        database: {
                          label:
                            dd._label ?? dd.label ?? database.fileName ?? '',
                          path: database.path || null,
                        },
                        reason: null,
                      };
                    }
                  }

                  return {
                    connectedServer: null,
                    database: null,
                    reason: 'No already-connected server was found.',
                  };
                }"""
            )
            result["diagnostics"]["connected_inventory"] = inventory

            if not inventory.get("connectedServer"):
                result["status"] = "needs_connection"
                result["checks"]["connected_server_available"] = False
                result["errors"].append(inventory.get("reason"))
                browser.close()
                raise SystemExit(2)

            if not inventory.get("database"):
                result["checks"]["connected_server_available"] = True
                result["checks"]["database_available"] = False
                result["errors"].append(inventory.get("reason"))
                browser.close()
                raise SystemExit(1)

            result["checks"]["connected_server_available"] = True
            result["checks"]["database_available"] = True
            page.wait_for_timeout(700)

            tree_shot = shots / "08-connected-database-tree.png"
            page.screenshot(path=str(tree_shot), full_page=True)
            result["screenshots"].append(str(tree_shot))

            # Query Tool: open only, never execute SQL.
            query_opened = False
            try:
                query_button = first_visible(
                    page.locator(
                        'button[aria-label="כלי השאילתות"], '
                        'button[aria-label="Query Tool"]'
                    )
                )
                if query_button is not None and query_button.is_enabled():
                    query_button.click(timeout=10000)
                else:
                    click_app_menu_item(
                        page,
                        ["כלים", "Tools"],
                        ["כלי השאילתות", "Query Tool"],
                    )

                query_frame = wait_for_query_frame(page)
                query_frame.wait_for_selector(".cm-editor", timeout=30000)
                editor_dir = query_frame.locator(".cm-editor").first.evaluate(
                    "(el) => getComputedStyle(el).direction"
                )
                html_dir = query_frame.locator("html").get_attribute("dir")
                body_text = query_frame.locator("body").inner_text(
                    timeout=10000
                )
                hebrew_markers = [
                    x
                    for x in (
                        "פלט נתונים",
                        "הודעות",
                        "התראות",
                        "היסטוריית שאילתות",
                    )
                    if x in body_text
                ]
                result["diagnostics"]["query_tool"] = {
                    "html_dir": html_dir,
                    "editor_direction": editor_dir,
                    "hebrew_markers": hebrew_markers,
                }
                result["checks"]["query_tool_visual"] = {
                    "opened": True,
                    "frame_rtl": html_dir == "rtl",
                    "editor_ltr": editor_dir == "ltr",
                    "hebrew_chrome": len(hebrew_markers) >= 2,
                }
                query_opened = True

                query_shot = shots / "09-query-tool.png"
                page.screenshot(path=str(query_shot), full_page=True)
                result["screenshots"].append(str(query_shot))
            except Exception as exc:
                result["checks"]["query_tool_visual"] = {
                    "opened": False,
                }
                result["errors"].append(f"Query Tool: {exc}")

            # Backup dialog: inspect only; never press Backup.
            try:
                click_app_menu_item(
                    page,
                    ["אובייקט", "Object"],
                    ["גיבוי...", "Backup..."],
                )
                backup_dialog = page.locator(".dock-fbox").filter(
                    has=page.locator('input[name="file"]')
                ).last
                backup_dialog.wait_for(state="visible", timeout=15000)
                page.wait_for_timeout(700)

                backup_visual = backup_dialog.evaluate(
                    """(el) => {
                      const file = el.querySelector('input[name="file"]');
                      return {
                        direction: getComputedStyle(el).direction,
                        fileDirection: file
                          ? getComputedStyle(file).direction
                          : null,
                        hasHorizontalOverflow:
                          el.scrollWidth > el.clientWidth + 1,
                      };
                    }"""
                )
                result["diagnostics"]["backup_dialog"] = backup_visual
                result["checks"]["backup_dialog_visual"] = {
                    "opened": True,
                    "dialog_rtl": backup_visual["direction"] == "rtl",
                    "file_ltr": backup_visual["fileDirection"] == "ltr",
                    "no_horizontal_overflow":
                        not backup_visual["hasHorizontalOverflow"],
                }

                backup_shot = shots / "10-backup-dialog.png"
                page.screenshot(path=str(backup_shot), full_page=True)
                result["screenshots"].append(str(backup_shot))
            except Exception as exc:
                result["checks"]["backup_dialog_visual"] = {
                    "opened": False,
                }
                result["errors"].append(f"Backup dialog: {exc}")
            finally:
                try:
                    close_float_dialog(page)
                except Exception:
                    pass

            # Restore dialog: inspect only; never press Restore.
            try:
                click_app_menu_item(
                    page,
                    ["אובייקט", "Object"],
                    ["שחזור...", "Restore..."],
                )
                restore_dialog = page.locator(".dock-fbox").filter(
                    has=page.locator('input[name="file"]')
                ).last
                restore_dialog.wait_for(state="visible", timeout=15000)
                page.wait_for_timeout(700)

                restore_visual = restore_dialog.evaluate(
                    """(el) => {
                      const file = el.querySelector('input[name="file"]');
                      return {
                        direction: getComputedStyle(el).direction,
                        fileDirection: file
                          ? getComputedStyle(file).direction
                          : null,
                        hasHorizontalOverflow:
                          el.scrollWidth > el.clientWidth + 1,
                      };
                    }"""
                )
                result["diagnostics"]["restore_dialog"] = restore_visual
                result["checks"]["restore_dialog_visual"] = {
                    "opened": True,
                    "dialog_rtl": restore_visual["direction"] == "rtl",
                    "file_ltr": restore_visual["fileDirection"] == "ltr",
                    "no_horizontal_overflow":
                        not restore_visual["hasHorizontalOverflow"],
                }

                restore_shot = shots / "11-restore-dialog.png"
                page.screenshot(path=str(restore_shot), full_page=True)
                result["screenshots"].append(str(restore_shot))
            except Exception as exc:
                result["checks"]["restore_dialog_visual"] = {
                    "opened": False,
                }
                result["errors"].append(f"Restore dialog: {exc}")
            finally:
                try:
                    close_float_dialog(page)
                except Exception:
                    pass

            required = [
                result["checks"].get("connected_server_available", False),
                result["checks"].get("database_available", False),
                all(
                    result["checks"].get(
                        "query_tool_visual", {}
                    ).values()
                ),
                all(
                    result["checks"].get(
                        "backup_dialog_visual", {}
                    ).values()
                ),
                all(
                    result["checks"].get(
                        "restore_dialog_visual", {}
                    ).values()
                ),
            ]
            result["status"] = "passed" if all(required) else "failed"

            # Closing the browser object only disconnects Playwright from CDP;
            # it does not terminate the Electron process.
            browser.close()

    except SystemExit as exc:
        code = int(exc.code or 0)
        report_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
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
