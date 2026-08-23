# Torah Pod Google Play submission

Prepared for the first Google Play release of `com.torahpod.app`.

## Current release candidate

- Version: `0.3.8` (`versionCode 14`)
- Signed bundle workflow: [32647514283](https://github.com/shaqo88/youtube-podcast-feeds/actions/runs/32647514283)
- Artifact: `torah-pod-release.aab`
- Track to use first: Internal testing, then Closed testing

## Store listing draft

### Short description (English)

Torah podcasts and lessons in one simple listening app.

### Full description (English)

Torah Pod brings Torah podcasts and lessons into one focused listening home. Browse available podcasts, follow the ones you want, find new episodes, and keep a personal queue for later.

Features:

- Browse Torah podcasts and recent episodes
- Follow podcasts and see new episodes from your library
- Add episodes to a queue and move them up or down
- Resume listening with saved progress
- Background playback with Android media controls
- Hebrew and English interface
- Open RSS feeds for compatible podcast apps

Torah Pod is free to use and does not require an account.

### Short description (Hebrew)

פודקאסטים ושיעורי תורה במקום אחד, להאזנה פשוטה ונוחה.

### Full description (Hebrew)

Torah Pod מרכז פודקאסטים ושיעורי תורה במקום אחד, עם חוויית האזנה פשוטה ונוחה.

אפשר לעיין בפודקאסטים, לעקוב אחרי התוכניות שמעניינות אתכם, לראות פרקים חדשים, להוסיף פרקים לתור ולהמשיך להאזין מהמקום שבו עצרתם.

העיקר בפנים:

- חיפוש פודקאסטים ופרקים
- ספרייה אישית של פודקאסטים במעקב
- תור האזנה שניתן לסדר מחדש
- שמירת התקדמות ההאזנה
- ניגון ברקע ושליטה דרך התראות Android
- ממשק בעברית ובאנגלית
- תמיכה בפידי RSS לאפליקציות פודקאסטים

Torah Pod חינמי ואינו דורש פתיחת חשבון.

## Release notes

גרסה ראשונה של Torah Pod: האזנה לפודקאסטים תורניים, ספרייה אישית, תור השמעה וניגון ברקע.

## Screenshots to capture

Capture the Play-installed app (not the debug APK), with no personal data visible:

1. Home: followed podcasts and recent episodes.
2. All podcasts/search screen.
3. Episode player expanded with title, progress, seek, speed and queue controls.
4. My Library showing followed podcasts.
5. Queue showing next/previous controls and the now-playing strip.
6. Android notification/media controls while playback is in the background.

Use the same language as the selected listing (Hebrew first; English can be added later). Avoid screenshots containing private feeds, emails, or test data.

## Data Safety draft (verify in Play Console)

The app has no account creation or sign-in. Library, queue, language, playback position, and preferences are stored locally in the browser/WebView storage. The app requests network access to load the Torah Pod site and audio feeds. The app does not intentionally sell data or use personalized advertising.

Before submitting the Data Safety form, verify whether Cloudflare Web Analytics is active for the production site and disclose any applicable aggregate usage measurement. If the native app ever adds authentication, analytics, crash reporting, or remote sync, this section must be updated.

## Privacy policy

The public site currently describes privacy in the About page:

`https://torah-pod.pages.dev/about/`

Play Console should receive a direct, publicly accessible privacy-policy URL. Prefer creating a dedicated `/privacy/` page before production submission, while keeping the same policy text linked inside the app.

## Testing plan

1. Finish Internal testing with the owner account and verify install/update/playback.
2. Create a Closed testing track.
3. Add at least 12 Google accounts as testers (required for newer personal developer accounts).
4. Keep at least 12 testers opted in continuously for 14 days.
5. Record tester feedback and fixes.
6. Apply for production access and answer Google’s closed-test questions.

