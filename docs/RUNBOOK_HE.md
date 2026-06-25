# מדריך תפעול קצר

## הוספת פודקאסט חדש

1. פותחים את טופס ההצטרפות:

   ```text
   https://shaqo88.github.io/youtube-podcast-feeds/onboard/
   ```

2. ממלאים את הפרטים. השדה `שם קצר לקישור באנגלית` חובה, לדוגמה:

   ```text
   rav-example
   ```

3. אחרי השליחה נוצר Issue בגיטהאב עם התווית `needs-approval`.

## אישור פודקאסט מתיקיית Drive

1. מריצים:

   ```text
   Actions -> Check Drive Folder -> Run workflow
   ```

2. מדביקים את קישור התיקייה ובודקים שיש לפחות קובץ אחד לפרסום.
3. אם הכל תקין, מוסיפים ל-Issue את התווית:

   ```text
   approved
   ```

4. GitHub Actions יוצר את הפודקאסט, מסנכרן פרקים ראשונים, מפרסם Feed,
   מוסיף תגובה עם הקישור, מסיר `needs-approval`, וסוגר את ה-Issue.

## אישור פודקאסט מיוטיוב

1. פותחים את הערוץ ובודקים שהוא הערוץ הנכון.
2. אם הכל תקין, מוסיפים ל-Issue את התווית:

   ```text
   approved
   ```

3. המערכת תנסה לזהות את מזהה הערוץ, לקחת תמונה מהערוץ אם לא סופקה תמונה,
   ליצור Config, לסנכרן פרקים ראשונים, ולפרסם Feed.

## מחיקת פודקאסט ניסיון

1. מוחקים את התיקיות:

   ```text
   shows/<slug>
   public/<slug>
   ```

2. דוחפים את השינוי ל-`main`.
3. מוחקים את קבצי האודיו מ-R2:

   ```text
   Actions -> Delete R2 Prefix -> Run workflow
   ```

4. מכניסים:

   ```text
   prefix=<slug>
   confirm=DELETE
   ```

## Nachmanson

הפודקאסט של הרב נחמנסון הועתק לריפו הזה עם הפרקים והתמונה מה-ripo הישן.
כרגע הוא מוגדר כ-`enabled: false`, כי מזהה הפלייליסט היה שמור כ-GitHub Secret
בריפו הישן ואי אפשר לקרוא ערך של Secret קיים. כדי להפעיל סנכרון עתידי צריך
להכניס את מזהה הפלייליסט ל-`shows/nachmanson/config.yml` ולהחליף
`enabled: false` ל-`enabled: true`.
