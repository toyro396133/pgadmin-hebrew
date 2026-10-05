# התקנת עברית + RTL ב־pgAdmin 4 v9.18 על Windows

> החבילה מיועדת ל־pgAdmin **9.18**. לפני שינוי קבצי התקנה מומלץ לסגור את pgAdmin.

## הדרך המומלצת — installer אוטומטי

פתח PowerShell בתיקיית החבילה והריץ:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-hebrew.ps1
```

הסקריפט ינסה לאתר התקנת pgAdmin יחידה. אם יש יותר מהתקנה אחת, או שהזיהוי נכשל, העבר במפורש את תיקיית `web`:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-hebrew.ps1 `
  -WebPath "C:\...\pgAdmin 4\web"
```

המתקין:

1. בודק ש־`version.py` מצביע על 9.18.
2. יוצר גיבוי חד־פעמי ל־`config.py` ול־`pgadmin\templates\base.html` לפני שינוי.
3. מוסיף `he: Hebrew` לרשימת השפות.
4. מוסיף RTL סמנטי לעברית בלבד.
5. משאיר CodeMirror, PSQL ואזורים טכניים נבחרים ב־LTR.
6. מעתיק את `messages.po` ו־`messages.mo` אל `pgadmin\translations\he\LC_MESSAGES`.
7. יוצר `.pgadmin-hebrew-9.18-install.json` כדי לאפשר שחזור מסודר.

ייתכן שתידרש פתיחת PowerShell כמנהל אם pgAdmin מותקן תחת `Program Files`.

### התקנה ללא RTL

אם רוצים לבדוק קודם רק את התרגום:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-hebrew.ps1 -NoRtl
```

### שחזור

```powershell
powershell -ExecutionPolicy Bypass -File .\install-hebrew.ps1 -Restore
```

אם ציינת `-WebPath` בהתקנה, מומלץ לציין אותו גם בשחזור.

## הפעלה ובחירת עברית

הפעל מחדש את pgAdmin. פתח:

`Preferences > User Interface > Language`

בחר `Hebrew`, שמור ובצע רענון/הפעלה מחדש אם pgAdmin מבקש זאת.

## התקנה ידנית

### 1. הוספת השפה

פתח `web\config.py`, אתר את `LANGUAGES`, והוסף אחרי English:

```python
'he': 'Hebrew',
```

### 2. העתקת הקטלוג

צור:

```text
web\pgadmin\translations\he\LC_MESSAGES\
```

והעתק לשם:

```text
messages.po
messages.mo
```

### 3. RTL

החל את `rtl-he.patch` על `web\pgadmin\templates\base.html`, או בצע את השינוי המתועד ב־`RTL.md`.

למי שעובד מתוך source tree ניתן להחיל את שני השינויים יחד באמצעות:

```text
pgadmin-hebrew-v9.18.patch
```

## בדיקת עשן

לאחר המעבר לעברית בדוק לפחות:

- סייר האובייקטים והמאפיינים של Server/Database/Schema/Table.
- Query Tool, Data Output והיסטוריית שאילתות.
- PSQL Tool.
- Backup/Restore ו־Import/Export.
- Preferences, Dashboard ו־User Management.
- שילובי עברית עם SQL, נתיבים, IP ושמות אובייקטים באנגלית.

לרשימת בדיקות RTL מלאה ראו `RTL.md`.
