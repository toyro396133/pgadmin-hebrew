# pgAdmin 4 v9.18 — לוקליזציה עברית

חבילת לוקליזציה עברית מלאה ברמת קטלוג gettext עבור pgAdmin 4 v9.18.

## עוגן המקור

- Release: `REL-9_18`
- pgAdmin: `9.18`
- תאריך יציאת הגרסה: `2026-09-17`
- קובץ upstream: `web/pgadmin/messages.pot`
- SHA של blob שנבדק: `3b48f12d1069a762de5abde8c60ee909b7e4ab87`
- `POT-Creation-Date`: `2026-09-15 17:11+0530`
- Toolchain: Babel 2.18.0

## מצב החבילה

- **3,684 / 3,684 מחרוזות מקור מכוסות (100%)**.
- `messages.po` ו־`messages.mo` נבנים מכל `translations.json`.
- בדיקות placeholders/markup עוברות ללא שגיאות.
- אין תווי BiDi/format נסתרים בתרגומים.
- סט מפתחות התרגום אומת מול `messages.pot` הרשמי של `REL-9_18`.

לסטטוס מפורט ראו `STATUS.md`.

## הקבצים העיקריים

- `translations.json` — מקור האמת של התרגומים המאושרים.
- `messages.po` — קטלוג עברי מוכן לשימוש.
- `messages.mo` — הקטלוג המקמפל.
- `glossary.md` — מדיניות ומילון מונחים.
- `qa_translation.py` — בדיקות מבנה, placeholders ו־BiDi.
- `verify_upstream.py` — מאמת התאמה מלאה ל־POT הרשמי ול־Git blob המדויק של `REL-9_18`.
- `verify_keyset.py` — בדיקת שלמות אופליין של 3,684 מפתחות התרגום מול טביעת האצבע של `REL-9_18`.
- `merge_into_template.py` — ממזג תרגומים לתוך POT upstream תוך שימור references/flags.
- `fetch-and-build.ps1` — תהליך מלא ל־Windows: הורדה, אימות, מיזוג, QA וקימפול.
- `INSTALL-WINDOWS.md` — הוראות התקנה.
- `install_hebrew.py` / `install-hebrew.ps1` — מתקין בטוח עם גיבוי ושחזור.
- `rtl-he.patch` — RTL סמנטי לעברית + החרגות LTR לאזורים טכניים.
- `pgadmin-hebrew-v9.18.patch` — patch משולב לרישום השפה ול־RTL.
- `verify_rtl.py` — QA אופליין ל־RTL ולמתקין.
- `RTL.md` — תכנון RTL ורשימת בדיקות UI.

## בנייה מלאה על Windows

דרוש Python עם Babel 2.18.0 או גרסה תואמת.

```powershell
pip install Babel==2.18.0
.\fetch-and-build.ps1
```

הסקריפט מוריד **רק** את `REL-9_18`, מאמת ש־`translations.json` תואם בדיוק לקטלוג הרשמי, ממזג את התרגומים, מריץ QA ומקמפל `messages.full.mo`.

## מבנה היעד ב־pgAdmin

```text
web/
├─ config.py
└─ pgadmin/
   └─ translations/
      └─ he/
         └─ LC_MESSAGES/
            ├─ messages.po
            └─ messages.mo
```

בנוסף יש להוסיף ל־`LANGUAGES` ב־`web/config.py`:

```python
'he': 'Hebrew',
```

הקובץ `config-he.patch` מכיל את השינוי המינימלי.

## QA

```powershell
python .\verify_keyset.py
python .\qa_translation.py .\messages.po
python .\verify_rtl.py
python .\verify_upstream.py .\messages-v9.18.pot
```

## RTL

החבילה כוללת RTL סמנטי + שכבת תיקוני UI שנבדקת מול pgAdmin Desktop 9.18 אמיתי. `base.html` מקבל `dir="rtl"` רק כאשר `PGADMIN_LANGUAGE=he`, ובמקביל CodeMirror, xterm, קוד, שדות חיבור/נתיבים ו־Data Grid נשארים LTR כדי לא לשבש SQL, כתובות, נתיבים וסדר עמודות.

נוספו תיקונים נקודתיים ל־Preferences, Object Explorer, תפריטים, rc-dock dialogs וטאבים. בפרט, כפתורי הסגירה של rc-dock נשארים בצד המקורי שלהם גם כשהכותרת עצמה RTL.

הפתרון אינו מחייב build מחדש של frontend ולכן מתאים גם להתקנת pgAdmin קיימת. ראו `RTL.md` ו־`STATUS.md` לכיסוי המאומת.

## בנייה ניתנת לשחזור

`build_catalog.py` משתמש בתאריך רוויזיה קבוע של החבילה, ולכן הרצה חוזרת על אותו `translations.json` מפיקה `messages.po` ו־`messages.mo` זהים ביט־לביט. `messages.po` שבשורש הוא קטלוג קומפקטי ומוכן לשימוש; `fetch-and-build.ps1` יכול לייצר גם `messages.full.po` במבנה ה־POT הרשמי, כולל references ו־flags.

## One-command Windows install + E2E visual QA

From a fresh clone, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-and-test.ps1
```

The runner installs the Hebrew localization into pgAdmin 4 v9.18, executes all
offline QA checks, launches the installed desktop runtime with Chromium DevTools,
checks Hebrew + RTL in the real UI, captures Dashboard/Object Explorer/menus/
Preferences/Register Server and the existing-server context menu, and commits +
pushes the screenshots and JSON report. Screenshots from the previous run are
deleted before capture, so Git always reflects the latest run.

The main runner now continues automatically into the connected QA stage after
the base Hebrew/RTL checks pass. It connects the registered `PostgreSQL 18`
server, and if pgAdmin requests a password the script waits while the user enters
it in the pgAdmin password dialog. Once connected, it creates or reuses the
dedicated `pgadmin_hebrew_e2e` database, connects to it, and checks Query Tool,
Backup and Restore visually. Backup and Restore are opened for inspection only;
their actions are never started.

Use `-KeepPgAdmin` only when you want the tested desktop process to remain open
after all base + connected tests finish:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-and-test.ps1 -KeepPgAdmin
```

The connected stage can also be rerun against an already-running pgAdmin
instance without reinstalling/restarting it:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-connected-e2e.ps1
```

If more than one pgAdmin installation is detected, pass the web directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-and-test.ps1 -WebPath "C:\Program Files\PostgreSQL\18\pgAdmin 4\web"
```
