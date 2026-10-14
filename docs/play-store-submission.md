# Torah Pod Google Play submission

Current as of 2026-10-14. The private intake repository's
`docs/google-play/PRODUCTION_RELEASE_CHECKLIST.md` is the production decision
record. This public note records only nonprivate implementation facts and copy.

## Android candidate

- Package: `com.torahpod.app`
- Current Play Internal testing release: `0.5.0` (`versionCode 19`).
- Android source: `b2fd0fdfe035ec199fc429217b934a50d4e3a447`. No
  `android-wrapper` source changes appeared through main
  `506ca0feb2ee5c6265be66bce0e65a502617652e`.
- Target SDK: 36. The app loads the production web site, which deploys
  independently of the Android bundle.
- No production release or promotion is authorized by this document.

## Store listing draft

**English short description:** Torah podcasts and lessons with an optional
listening account.

**English full description:**

Torah Pod brings Torah podcasts and lessons into one listening home. Browse
shows and episodes, follow the ones you want, save episodes, and build a
listening queue. Playback supports seeking, speed controls, background audio,
and Android media controls. The interface is available in Hebrew and English.
Listening works without an account. An optional Google account synchronizes
your library and listening progress across devices and gives you account
export and deletion controls. Torah Pod is free and has no personalized ads.
Some audio, artwork, and feeds are supplied by external content providers.

**Hebrew short description:** פודקאסטים ושיעורי תורה עם ספרייה אישית וחשבון אופציונלי.

**Hebrew full description:**

Torah Pod מרכז פודקאסטים ושיעורי תורה במקום אחד. אפשר לעיין בתוכניות ובפרקים,
לעקוב אחרי פודקאסטים, לשמור פרקים ולהכין תור האזנה. הנגן תומך בדילוג, שינוי
מהירות, האזנה ברקע ובקרי מדיה של Android. הממשק זמין בעברית ובאנגלית.
אפשר להאזין ללא חשבון. חשבון Google אופציונלי מסנכרן את הספרייה והתקדמות
ההאזנה בין מכשירים, ומאפשר ייצוא ומחיקה של נתוני החשבון. השימוש חינמי וללא
פרסום מותאם אישית. חלק מהשמע, התמונות והפידים מגיעים מספקי תוכן חיצוניים.

## Release notes draft for 0.5.0

**English:** Optional Google sign-in now lets you synchronize followed
podcasts, saved episodes, and listening progress across devices. Guest
listening remains available.

**Hebrew:** כניסה אופציונלית עם Google מאפשרת לסנכרן פודקאסטים במעקב, פרקים
שמורים והתקדמות האזנה בין מכשירים. אפשר להמשיך להאזין גם ללא חשבון.

## Policy and visual material

- The current public privacy text is at `https://torah-pod.pages.dev/terms/`.
  It needs a complete retention and data-handling update before production.
- The account-deletion web resource is prepared at
  `public/account-deletion/index.html`. Verify its live URL and browser
  deletion flow before entering it in Play Console.
- Do not submit an old “no accounts” Data Safety or App access answer.
- Capture store screenshots from the Play-installed release with no personal
  data visible. Show the current navigation, player, library, queue, and
  optional account flow accurately. The icon and feature graphic also need
  visual review in Console.
