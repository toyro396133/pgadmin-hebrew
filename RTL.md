# RTL לעברית ב־pgAdmin 4 v9.18

## מה החבילה עושה

`rtl-he.patch` ו־`install_hebrew.py` מוסיפים ל־`web/pgadmin/templates/base.html` כיוון סמנטי לפי השפה שנבחרה:

```html
<html lang="he" dir="rtl">
```

כאשר נבחרת שפה שאינה עברית, הכיוון נשאר `ltr`.

הפתרון יושב ב־`base.html` ולא ב־CSS שנבנה באמצעות webpack, ולכן הוא מתאים גם להתקנת pgAdmin קיימת ואינו דורש build מחדש של frontend.

## אזורים שנשארים LTR בכוונה

גם בממשק עברי יש אזורים שבהם שינוי כיוון עלול לפגוע בקריאות או בסדר הנתונים. לכן החבילה מחזירה ל־LTR באופן מפורש:

- CodeMirror / עורך SQL.
- xterm / כלי PSQL.
- `pre`, `code`, `kbd`, `samp`.
- קלט מספרי, סיסמאות, כתובות דוא"ל ו־URL.
- React Data Grid (`.rdg`) כדי לשמור על סדר עמודות תוצאת SQL.

## מה עדיין דורש בדיקת UI אמיתית

ה־RTL הנוכחי הוא baseline שמרני להתקנה קיימת. pgAdmin 9.18 משתמש ב־MUI/Emotion אך אינו כולל תשתית RTL מלאה של MUI. לכן עדיין יש לבצע בדיקה חזותית ולחפש:

- אייקונים או חצים שצריכים להתהפך.
- `margin-left`/`margin-right` פיזיים ברכיבים מסוימים.
- דיאלוגים שמופיעים דרך Portal.
- tabs, accordions ותפריטי הקשר.
- שדות טקסט טכניים מסוג `text` שבהם הערך הוא host/path/identifier.
- חיתוך טקסט בכפתורים ובכותרות ארוכות בעברית.

## בדיקת RTL אופליין

```powershell
python .\verify_rtl.py
```

הבדיקה מאמתת:

- ש־fixture של `base.html` הוא בדיוק ה־blob הרשמי של `REL-9_18`.
- שה־patch מייצר Jinja תקין.
- שה־patch אידמפוטנטי.
- שה־installer יודע להתקין ולשחזר מתוך עץ pgAdmin זמני.
- שקיימות החרגות LTR ל־CodeMirror, xterm ו־React Data Grid.

## בדיקת UI מומלצת

לאחר התקנה והפעלת עברית, בדוק בסדר הבא:

1. Login / Preferences.
2. Object Explorer ותפריט ראשי.
3. Properties של Server / Database / Schema / Table.
4. Query Tool, כולל Find/Replace, EXPLAIN ו־Data Output.
5. PSQL Tool.
6. Backup / Restore / Import-Export.
7. Dashboard, Sessions, Locks ו־Logs.
8. Dialogs עם שילוב עברית + SQL/host/path/IP.

כל חריגה שתתגלה במסכים האלה צריכה לקבל selector נקודתי, ולא שינוי כיוון גורף נוסף.
