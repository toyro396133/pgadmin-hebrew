# סטטוס לוקליזציית pgAdmin 4 v9.18 לעברית

## כיסוי

- מקור: `pgadmin-org/pgadmin4`, תג `REL-9_18`
- `POT-Creation-Date`: `2026-09-15 17:11+0530`
- מספר מחרוזות המקור: **3,684**
- מספר מפתחות ב־`translations.json`: **3,684**
- כיסוי קטלוג: **100%**
- מחרוזות ריקות בקטלוג הבנוי: **0**

סט המפתחות נבדק מול `web/pgadmin/messages.pot` הרשמי של `REL-9_18`. שתי חריגות שנכנסו במהלך העבודה (`Queries`, `Roles`) הוסרו, ושתי מחרוזות המקור שחסרו הושלמו.

## QA אוטומטי

הבדיקות מאמתות:

- placeholders בסגנון `%s`, `%(name)s`, `{0}`, `{error}` ו־`${...}`.
- תגי HTML נפוצים המוטמעים במחרוזות.
- היעדר תווי BiDi/format נסתרים בקטלוג העברי.
- אפשרות לקמפל את `messages.po` ל־`messages.mo` בעזרת Babel.
- התאמה מלאה בין סט מפתחות התרגום לסט מחרוזות המקור של 9.18 באמצעות `verify_upstream.py`; בנוסף `verify_keyset.py` מאפשר אימות שלמות אופליין מול טביעת האצבע של אותו קטלוג.

## ליטוש לשוני שבוצע

- `Database` → **מסד נתונים**.
- `Schema` → **סכימה**.
- `Object Explorer` → **סייר האובייקטים**.
- `Query Tool` → **כלי השאילתות**.
- `Replication Slot` → **חריץ שכפול**.
- `Tuple/Tuples` → **טופל/טופלים**.
- `Synonym` → **שם נרדף**.
- פקודות ומילות מפתח רשמיות של PostgreSQL, כגון `VACUUM`, `ANALYZE`, `EXPLAIN`, `COMMIT`/`ROLLBACK` בהקשרים טכניים, נשמרות בצורתן המקובלת כשזה מונע עמימות.

## RTL

- נוסף RTL סמנטי לעברית באמצעות `dir="rtl"` ב־`base.html`.
- CodeMirror, xterm, `pre/code`, שדות חיבור/נתיבים טכניים ו־React Data Grid מוחזרים ל־LTR בכוונה.
- נוספה שכבת RTL חזותית ל־Preferences, Object Explorer, תפריטים, טפסים ו־rc-dock dialogs.
- תוויות תצוגה קשיחות של pgAdmin כגון `Open` ו־`Servers` מותאמות לעברית בזמן ריצה בלי לשנות ערכים שמורים.
- `verify_rtl.py` עבר: SHA של fixture upstream, Jinja parse, LF/CRLF, idempotency, שדרוג RTL/runtime ו־install/restore smoke test.
- נוסף installer אוטומטי עם גיבוי ושחזור, כולל self-elevation ב־Windows כאשר pgAdmin מותקן תחת `Program Files`.

## QA חזותי / E2E בפועל

ה־E2E האמיתי מול pgAdmin Desktop 9.18 עבר בהצלחה ב־2026-10-06 ומכסה כרגע:

- טעינת עברית דרך Preferences API.
- `html lang="he"`, `dir="rtl"` ו־RTL מחושב של הגוף.
- Dashboard וטאבים מרכזיים בעברית.
- Object Explorer ב־RTL, כולל תצוגת קבוצת ברירת המחדל כ־**שרתים**.
- תפריט `⋮` ותפריטי הקשר ב־RTL.
- Preferences, כולל divider נכון, גלילה אופקית מוסתרת וטקסטי עזרה.
- חלון **רישום שרת** וכרטיסיית **חיבור**.
- Host / Port / DB / Username / Password / Service ב־LTR.
- תפריט ההקשר של השרת הקיים `PostgreSQL 18`.
- בדיקה מפורשת שמצב החיבור של שרת מנותק נשאר ללא שינוי במהלך האודיט.
- שמירת screenshots ודוח JSON בכל סבב, וניקוי artifacts קודמים לפני הסבב הבא.

בסבב המאומת האחרון:

- `ui_ready.bodyTextLength = 451`
- `ui_ready.treeRows = 1`
- `server_inventory_loaded = true`
- `PostgreSQL 18` זוהה כ־`connected: false`
- `server_connection_state_preserved = true`
- סטטוס E2E כולל: **passed**

## מה עדיין אינו “סגור” לחלוטין

תרחישים שתלויים בשרת/מסד **שכבר מחוברים מראש** עדיין אינם מכוסים אוטומטית בסבב הבטוח:

- Query Tool.
- Backup.
- Restore.
- תרחישים עמוקים יותר בתוך מסדי נתונים, סכימות, טבלאות וגרידים.

ה־E2E לא מחבר שרת מנותק מאחורי הקלעים רק כדי להשיג כיסוי. כאשר יש שרת שכבר מחובר לפני הריצה, אפשר להרחיב את שכבת הבדיקות הזו בלי לשנות מצב חיבור או נתוני משתמש.

## שחזוריות

הבנייה של הקטלוג הקומפקטי היא דטרמיניסטית: שתי הרצות רצופות מאותו `translations.json` הפיקו אותו digest בדיוק. כך ניתן לזהות שינוי אמיתי בתרגום בלי רעש שנובע מזמן הבנייה.
