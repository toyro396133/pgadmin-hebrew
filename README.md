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

החבילה כוללת כעת **RTL baseline עובד** ל־Hebrew. `base.html` מקבל `dir="rtl"` רק כאשר `PGADMIN_LANGUAGE=he`, ובמקביל CodeMirror, xterm, קוד ו־Data Grid נשארים LTR כדי לא לשבש SQL וסדר עמודות.

הפתרון אינו מחייב build מחדש של frontend ולכן מתאים גם להתקנת pgAdmin קיימת. הוא עדיין דורש סבב בדיקות חזותי בתוך pgAdmin, משום ש־9.18 אינו כולל תשתית מלאה למירור רכיבי MUI/Emotion. ראו `RTL.md`.


## בנייה ניתנת לשחזור

`build_catalog.py` משתמש בתאריך רוויזיה קבוע של החבילה, ולכן הרצה חוזרת על אותו `translations.json` מפיקה `messages.po` ו־`messages.mo` זהים ביט־לביט. `messages.po` שבשורש הוא קטלוג קומפקטי ומוכן לשימוש; `fetch-and-build.ps1` יכול לייצר גם `messages.full.po` במבנה ה־POT הרשמי, כולל references ו־flags.

## One-command Windows install + E2E visual QA

From a fresh clone, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-and-test.ps1
```

The runner installs the Hebrew localization into pgAdmin 4 v9.18, executes all
offline QA checks, launches the installed desktop runtime with Chromium DevTools,
checks Hebrew + RTL in the real UI, captures the main screen/File menu/Preferences,
and commits + pushes the new screenshots and JSON report. Screenshots from the
previous run are deleted before capture, so Git always reflects the latest run.

If more than one pgAdmin installation is detected, pass the web directory:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-and-test.ps1 -WebPath "C:\Program Files\PostgreSQL\18\pgAdmin 4\web"
```
