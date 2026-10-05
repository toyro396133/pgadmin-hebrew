# מילון מונחים מחייב — pgAdmin 4 בעברית

גרסה: pgAdmin 4 v9.18 (`REL-9_18`)

המטרה היא עקביות: אותו מושג מקבל אותו תרגום בכל הממשק, אלא אם ההקשר הטכני מחייב אחרת.

| English | עברית | הערה |
|---|---|---|
| Database | מסד נתונים | לא "בסיס נתונים" |
| Server | שרת | |
| Object Explorer | סייר האובייקטים | |
| Schema | סכימה | מונח PostgreSQL מקובל |
| Table | טבלה | |
| View | תצוגה | |
| Materialized View | תצוגה ממומשת | מונח מקובל יותר במערכות מסדי נתונים |
| Function | פונקציה | |
| Procedure | פרוצדורה | נשמרת ההבחנה מול Function |
| Role | תפקיד | PostgreSQL Role |
| User | משתמש | משתמש pgAdmin/מערכת לפי ההקשר |
| Trigger | טריגר | |
| Constraint | אילוץ | |
| Index | אינדקס | |
| Sequence | רצף | |
| Extension | הרחבה | |
| Tablespace | מרחב טבלאות | |
| Query | שאילתה | |
| Query Tool | כלי השאילתות | |
| Data Output | פלט נתונים | |
| Backup | גיבוי | |
| Restore | שחזור | |
| Maintenance | תחזוקה | |
| Preferences | העדפות | |
| Properties | מאפיינים | |
| Dependencies | תלויות | |
| Dependents | אובייקטים תלויים | כדי להבחין מ-Dependencies |
| Privileges | הרשאות | |
| Owner | בעלים | |
| Authentication | אימות | |
| Authorization | הרשאה | לא לערבב עם Authentication |
| Login | התחברות | |
| Logout | התנתקות | |
| Refresh | רענון | |
| Save | שמירה | |
| Cancel | ביטול | |
| Delete | מחיקה | |
| Edit | עריכה | |
| Create | יצירה | |
| Node | צומת | ברבים: צמתים |
| Browser | דפדפן | כאשר הכוונה לדפדפן; Object Explorer מתורגם בנפרד |
| Log | יומן | |
| Statistics | סטטיסטיקות | |
| Connection | חיבור | |
| Replication Slot | חריץ שכפול | מושג PostgreSQL; ברבים: חריצי שכפול |
| Tuple | טופל | ברבים: טופלים; נשמרת ההבחנה מ־Row |
| Synonym | שם נרדף | אובייקט DB/EDB, לא תרגום מילולי חופשי לפי הקשר |

## מונחים שלא מתרגמים

שמות פקודות, פרוטוקולים, מזהים ומותגים נשארים בצורתם הקנונית: `PostgreSQL`, `pgAdmin`, `SQL`, `VACUUM`, `ANALYZE`, `EXPLAIN`, `WAL`, `OID`, `PL/pgSQL`, `LDAP`, `TLS`, `GSSAPI`, `Kerberos`, `OAuth2`, `OIDC`, `TOTP`, `CSV`, `JSON`, `URI`, `URL`.

## BiDi ו-RTL

בתוך משפט עברי שומרים placeholders, נתיבים, שמות אובייקטים, כתובות, SQL וקוד בדיוק כפי שהם במקור. אין להוסיף תווי RTL/LTR נסתרים למחרוזות אלא במקרה מוכח שבו הרינדור נשבר; עדיף לפתור כיווניות בשכבת הממשק.

## כלל חשוב ל-Commit

`Commit` משמש ב-pgAdmin גם למידע על commit של קוד וגם לפעולת transaction. מאחר ששני ההקשרים חולקים אותו `msgid`, הוא נשאר כרגע `Commit` כדי לא לתת תרגום מטעה באחד המסכים. אם upstream יוסיף context (`msgctxt`) אפשר לתרגם כל שימוש בנפרד.
