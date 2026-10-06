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


DEFAULT_DATABASE = "pgadmin_hebrew_e2e"
DEFAULT_SERVER = "PostgreSQL 18"


def first_visible(locator):
    for i in range(locator.count()):
        item = locator.nth(i)
        try:
            if item.is_visible():
                return item
        except PlaywrightError:
            pass
    return None


def click_app_menu_item(page, menu_labels, item_labels):
    menu = first_visible(
        page.locator(
            ", ".join(
                f'button[data-label="{label}"]'
                for label in menu_labels
            )
        )
    )
    if menu is None:
        raise RuntimeError(
            f"App menu button not found: {', '.join(menu_labels)}"
        )
    menu.click(timeout=10000)

    item = first_visible(
        page.locator(
            ", ".join(
                f'li[data-label="{label}"]'
                for label in item_labels
            )
        )
    )
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
    extra = first_visible(page.locator(".dock-fbox .dock-extra-content"))
    if extra is not None:
        try:
            extra.click(timeout=5000)
            page.wait_for_timeout(500)
            return
        except PlaywrightError:
            pass

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


def server_snapshot(page, preferred_server):
    return page.evaluate(
        """async ({preferred}) => {
          const tree = window.pgAdmin?.Browser?.tree;
          if (!tree) throw new Error('pgAdmin Browser tree is unavailable');

          const servers = [];
          for (const group of tree.children() || []) {
            const gd = tree.itemData(group) || {};
            if (gd._type !== 'server_group') continue;
            if (tree.isClosed(group)) await tree.open(group);
            await tree.ensureLoaded(group);

            for (const server of tree.children(group) || []) {
              const sd = tree.itemData(server) || {};
              if (sd._type !== 'server') continue;
              servers.push({
                label: sd._label ?? sd.label ?? server.fileName ?? '',
                path: server.path || null,
                connected: Boolean(sd.connected),
                isConnecting: Boolean(sd.is_connecting),
                icon: sd.icon || '',
              });
            }
          }

          const selected =
            servers.find((x) => x.label === preferred)
            || servers[0]
            || null;
          return {selected, servers};
        }""",
        {"preferred": preferred_server},
    )


def trigger_server_connect(page, server_path):
    return page.evaluate(
        """({path}) => {
          const pgBrowser = window.pgAdmin?.Browser;
          const tree = pgBrowser?.tree;
          if (!tree) throw new Error('pgAdmin Browser tree is unavailable');

          let server = null;
          for (const group of tree.children() || []) {
            const gd = tree.itemData(group) || {};
            if (gd._type !== 'server_group') continue;
            server = (tree.children(group) || []).find(
              (item) => item.path === path
            );
            if (server) break;
          }
          if (!server) throw new Error('Server node not found: ' + path);

          const nodeObj = pgBrowser.Nodes?.server;
          if (!nodeObj?.callbacks?.connect_server) {
            throw new Error('Server connect callback is unavailable');
          }
          nodeObj.callbacks.connect_server.call(
            nodeObj,
            {item: server}
          );
          return true;
        }""",
        {"path": server_path},
    )


def visible_password_prompt(page):
    try:
        password = first_visible(
            page.locator(
                'input[type="password"], '
                'input[name="password"], '
                'input[name="master_password"]'
            )
        )
        if password is None:
            return False
        return True
    except PlaywrightError:
        return False


def wait_for_server_connection(
    page,
    preferred_server,
    timeout_s,
    result,
):
    snapshot = server_snapshot(page, preferred_server)
    server = snapshot.get("selected")
    result["diagnostics"]["server_before_connect"] = snapshot
    if not server:
        raise RuntimeError("No pgAdmin server is registered.")

    if server.get("connected"):
        result["checks"]["server_connected"] = True
        result["diagnostics"]["password_prompt_seen"] = False
        return server

    trigger_server_connect(page, server["path"])
    print(
        "Connecting to pgAdmin server. "
        "If a password dialog appears, enter the password in pgAdmin; "
        "the test will continue automatically.",
        flush=True,
    )

    deadline = time.monotonic() + timeout_s
    prompt_announced = False
    prompt_seen = False
    last = server

    while time.monotonic() < deadline:
        snap = server_snapshot(page, preferred_server)
        last = snap.get("selected") or last
        if last and last.get("connected"):
            result["checks"]["server_connected"] = True
            result["diagnostics"]["password_prompt_seen"] = prompt_seen
            result["diagnostics"]["server_after_connect"] = last
            return last

        if visible_password_prompt(page):
            prompt_seen = True
            if not prompt_announced:
                print(
                    "Password required: pgAdmin is waiting for input "
                    "in its password dialog. Enter it there and submit.",
                    flush=True,
                )
                prompt_announced = True

        time.sleep(0.5)

    result["diagnostics"]["password_prompt_seen"] = prompt_seen
    result["diagnostics"]["server_connect_timeout_state"] = last
    raise RuntimeError(
        f"Server did not connect within {timeout_s} seconds."
    )


def database_inventory(page, server_path, database_name):
    return page.evaluate(
        """async ({serverPath, databaseName}) => {
          const pgBrowser = window.pgAdmin?.Browser;
          const tree = pgBrowser?.tree;
          if (!tree) throw new Error('pgAdmin Browser tree is unavailable');

          let server = null;
          for (const group of tree.children() || []) {
            const gd = tree.itemData(group) || {};
            if (gd._type !== 'server_group') continue;
            server = (tree.children(group) || []).find(
              (item) => item.path === serverPath
            );
            if (server) break;
          }
          if (!server) throw new Error('Server node not found: ' + serverPath);

          const sd = tree.itemData(server) || {};
          if (!sd.connected) {
            return {
              serverConnected: false,
              collectionPath: null,
              database: null,
              databases: [],
              canCreateDatabase: false,
            };
          }

          if (tree.isClosed(server)) await tree.open(server);
          await tree.ensureLoaded(server);

          const collection = (tree.children(server) || []).find(
            (item) => (tree.itemData(item) || {})._type === 'coll-database'
          );
          if (!collection) {
            throw new Error('Database collection not found.');
          }

          if (tree.isClosed(collection)) await tree.open(collection);
          await tree.ensureLoaded(collection);

          const databases = (tree.children(collection) || [])
            .filter(
              (item) => (tree.itemData(item) || {})._type === 'database'
            )
            .map((item) => {
              const d = tree.itemData(item) || {};
              return {
                label: d._label ?? d.label ?? item.fileName ?? '',
                path: item.path || null,
                connected: Boolean(d.connected),
                allowConn: d.allowConn !== false,
              };
            });

          const database =
            databases.find((x) => x.label === databaseName) || null;

          return {
            serverConnected: true,
            collectionPath: collection.path || null,
            database,
            databases,
            canCreateDatabase: Boolean(sd.user?.can_create_db),
          };
        }""",
        {
            "serverPath": server_path,
            "databaseName": database_name,
        },
    )


def open_create_database_dialog(page, server_path):
    return page.evaluate(
        """async ({serverPath}) => {
          const pgBrowser = window.pgAdmin?.Browser;
          const tree = pgBrowser?.tree;
          if (!tree) throw new Error('pgAdmin Browser tree is unavailable');

          let server = null;
          for (const group of tree.children() || []) {
            const gd = tree.itemData(group) || {};
            if (gd._type !== 'server_group') continue;
            server = (tree.children(group) || []).find(
              (item) => item.path === serverPath
            );
            if (server) break;
          }
          if (!server) throw new Error('Server node not found: ' + serverPath);

          if (tree.isClosed(server)) await tree.open(server);
          await tree.ensureLoaded(server);

          const collection = (tree.children(server) || []).find(
            (item) => (tree.itemData(item) || {})._type === 'coll-database'
          );
          if (!collection) {
            throw new Error('Database collection not found.');
          }

          const nodeObj = pgBrowser.Nodes?.database;
          if (!nodeObj?.callbacks?.show_obj_properties) {
            throw new Error('Database create callback is unavailable.');
          }
          nodeObj.callbacks.show_obj_properties.call(
            nodeObj,
            {action: 'create', item: collection}
          );
          return {collectionPath: collection.path || null};
        }""",
        {"serverPath": server_path},
    )


def ensure_database(
    page,
    server_path,
    database_name,
    shots,
    result,
):
    inventory = database_inventory(page, server_path, database_name)
    result["diagnostics"]["database_inventory_before"] = inventory

    if inventory.get("database"):
        result["checks"]["database_created_or_reused"] = True
        result["diagnostics"]["database_created_this_run"] = False
        return inventory["database"]

    if not inventory.get("canCreateDatabase"):
        raise RuntimeError(
            "Connected PostgreSQL user does not have CREATE DATABASE permission."
        )

    open_create_database_dialog(page, server_path)
    dialog = page.locator(".dock-fbox").filter(
        has=page.locator('input[name="name"]')
    ).last
    dialog.wait_for(state="visible", timeout=20000)
    page.wait_for_timeout(700)

    name_input = dialog.locator('input[name="name"]')
    name_input.fill(database_name)

    create_shot = shots / "08-create-database.png"
    page.screenshot(path=str(create_shot), full_page=True)
    result["screenshots"].append(str(create_shot))

    save = first_visible(
        dialog.locator(
            'button[data-label="שמירה"], '
            'button[data-label="Save"]'
        )
    )
    if save is None:
        raise RuntimeError("Database dialog Save button was not found.")

    save.click(timeout=10000)

    # Wait until the create dialog closes successfully.
    try:
        dialog.wait_for(state="hidden", timeout=30000)
    except PlaywrightError:
        # Surface any visible form error in the report.
        text = dialog.inner_text(timeout=5000)
        raise RuntimeError(
            "Database create dialog did not close after Save. "
            f"Visible text: {text[:500]}"
        )

    deadline = time.monotonic() + 30
    last = None
    while time.monotonic() < deadline:
        last = database_inventory(page, server_path, database_name)
        if last.get("database"):
            result["checks"]["database_created_or_reused"] = True
            result["diagnostics"]["database_created_this_run"] = True
            result["diagnostics"]["database_inventory_after"] = last
            return last["database"]
        time.sleep(0.5)

    raise RuntimeError(
        f'Database "{database_name}" was saved but did not appear in the tree.'
    )


def trigger_database_connect(page, database_path):
    return page.evaluate(
        """({path}) => {
          const pgBrowser = window.pgAdmin?.Browser;
          const tree = pgBrowser?.tree;
          if (!tree) throw new Error('pgAdmin Browser tree is unavailable');

          let database = null;
          for (const group of tree.children() || []) {
            const gd = tree.itemData(group) || {};
            if (gd._type !== 'server_group') continue;
            for (const server of tree.children(group) || []) {
              const sd = tree.itemData(server) || {};
              if (sd._type !== 'server') continue;
              for (const collection of tree.children(server) || []) {
                if (
                  (tree.itemData(collection) || {})._type !== 'coll-database'
                ) continue;
                database = (tree.children(collection) || []).find(
                  (item) => item.path === path
                );
                if (database) break;
              }
              if (database) break;
            }
            if (database) break;
          }
          if (!database) {
            throw new Error('Database node not found: ' + path);
          }

          tree.select(database, true);
          const data = tree.itemData(database) || {};
          if (!data.connected && data.allowConn !== false) {
            const nodeObj = pgBrowser.Nodes?.database;
            nodeObj?.callbacks?.connect_database?.call(
              nodeObj,
              {item: database}
            );
          }
          return true;
        }""",
        {"path": database_path},
    )


def wait_for_database_connection(
    page,
    server_path,
    database_name,
    timeout_s,
    result,
):
    inventory = database_inventory(page, server_path, database_name)
    db = inventory.get("database")
    if not db:
        raise RuntimeError(f'Database "{database_name}" is missing.')

    if db.get("connected"):
        result["checks"]["database_connected"] = True
        return db

    trigger_database_connect(page, db["path"])
    deadline = time.monotonic() + timeout_s
    prompt_announced = False

    while time.monotonic() < deadline:
        inventory = database_inventory(page, server_path, database_name)
        db = inventory.get("database")
        if db and db.get("connected"):
            result["checks"]["database_connected"] = True
            result["diagnostics"]["database_after_connect"] = db
            return db

        if visible_password_prompt(page) and not prompt_announced:
            print(
                "Database connection is waiting for a password in pgAdmin. "
                "Enter it in the visible dialog and submit.",
                flush=True,
            )
            prompt_announced = True

        time.sleep(0.5)

    raise RuntimeError(
        f'Database "{database_name}" did not connect within {timeout_s} seconds.'
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp", required=True)
    ap.add_argument("--screenshots", default="artifacts/screenshots")
    ap.add_argument(
        "--report",
        default="artifacts/connected-e2e-report.json",
    )
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--database", default=DEFAULT_DATABASE)
    ap.add_argument("--password-wait-seconds", type=int, default=900)
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
            "server_requested": args.server,
            "database_requested": args.database,
        },
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

            server = wait_for_server_connection(
                page,
                args.server,
                args.password_wait_seconds,
                result,
            )
            result["checks"]["server_available"] = True

            database = ensure_database(
                page,
                server["path"],
                args.database,
                shots,
                result,
            )
            result["diagnostics"]["test_database"] = database

            database = wait_for_database_connection(
                page,
                server["path"],
                args.database,
                args.password_wait_seconds,
                result,
            )
            result["checks"]["database_available"] = True

            page.wait_for_timeout(700)
            tree_shot = shots / "09-connected-database-tree.png"
            page.screenshot(path=str(tree_shot), full_page=True)
            result["screenshots"].append(str(tree_shot))

            # Query Tool: open only. The database creation above is the only
            # intentional mutation in this connected stage.
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

                query_shot = shots / "10-query-tool.png"
                page.screenshot(path=str(query_shot), full_page=True)
                result["screenshots"].append(str(query_shot))

                close_tab = first_visible(
                    page.locator(
                        'div[data-dockid="id-main"] '
                        '.dock-tab.dock-tab-active .dock-tab-close-btn, '
                        'div[data-dockid="id-main"] '
                        '.dock-tab.dock-tab-active button[data-label="סגירה"], '
                        'div[data-dockid="id-main"] '
                        '.dock-tab.dock-tab-active button[data-label="Close"]'
                    )
                )
                if close_tab is not None:
                    close_tab.click(timeout=5000)
                    page.wait_for_timeout(700)
            except Exception as exc:
                result["checks"]["query_tool_visual"] = {"opened": False}
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

                backup_shot = shots / "11-backup-dialog.png"
                page.screenshot(path=str(backup_shot), full_page=True)
                result["screenshots"].append(str(backup_shot))
            except Exception as exc:
                result["checks"]["backup_dialog_visual"] = {"opened": False}
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

                restore_shot = shots / "12-restore-dialog.png"
                page.screenshot(path=str(restore_shot), full_page=True)
                result["screenshots"].append(str(restore_shot))
            except Exception as exc:
                result["checks"]["restore_dialog_visual"] = {"opened": False}
                result["errors"].append(f"Restore dialog: {exc}")
            finally:
                try:
                    close_float_dialog(page)
                except Exception:
                    pass

            required = [
                result["checks"].get("server_available", False),
                result["checks"].get("server_connected", False),
                result["checks"].get(
                    "database_created_or_reused", False
                ),
                result["checks"].get("database_available", False),
                result["checks"].get("database_connected", False),
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
