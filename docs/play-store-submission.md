# Torah Pod Google Play submission

Release and store-listing notes for `com.torahpod.app`.

## 0.4.0 internal release

The destination-based Home, Subscriptions, Search, Queue, mini-player, and
full-player redesign passed branch-preview, feed/site, and Android debug-build
validation and was merged to the production web app. `0.4.0` (`versionCode 17`)
is the intentional Internal Testing release. Publish only through both protected
Google Play approvals; do not promote it automatically to Closed or Production.

Internal release notes:

> A redesigned podcast experience with clearer Home, Subscriptions, Search,
> and Queue destinations; full-catalog episode search; new-episode badges; and
> a new mini-player and full-screen player. Existing subscriptions, queue,
> progress, played state, language, and playback speed are preserved.

After the Play update, repeat playback, background controls, offline retry,
queue autoplay/reordering, saved-state, and stale-notification acceptance checks
from the current release checklist.

## Current release candidate

- Version: `0.4.0` (`versionCode 17`)
- Signed bundle workflow: protected CI build and Internal Testing publication
- Artifact: `torah-pod-release.aab`
- Track for this rollout: Internal testing only; do not promote to production
- Existing tester opt-in link: `https://play.google.com/apps/internaltest/4701573172518535668`

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

חוויה חדשה וברורה יותר עם בית, פודקאסטים במעקב, חיפוש מלא, תור האזנה, נגן מוקטן ונגן במסך מלא. המינויים, התור וההתקדמות נשמרים.

A redesigned podcast experience with clearer Home, Subscriptions, Search and Queue, plus a new mini-player and full-screen player. Existing subscriptions, queue and progress are preserved.

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

## 0.4.0 internal acceptance

The publishing workflow runs only for an intentional change to
`android-wrapper/release-version.json`. It requires approval in the protected
release environment before signing and approval in the protected internal
environment before uploading. It always targets the Play `internal` track.

On a device with the Play-installed `0.3.10`:

1. Update through Google Play and confirm About/footer reports App `0.4.0`.
2. Play, pause, seek back 15 seconds, seek forward 30 seconds, and change speed.
3. Background playback for five minutes and repeat the controls from the lock screen.
4. Disconnect networking during startup, reconnect, and retry without losing the selected episode, queue, or saved position.
5. Switch episodes and let the queue advance automatically; confirm an old episode cannot display a stale error.
6. Close or swipe away the app after HTML playback and confirm no ghost notification remains.
7. If native playback was explicitly enabled, confirm genuine native background playback remains active when expected.
8. Reopen the app and resume from the saved position.
9. Verify controls, failure messages, retry, and About diagnostics in Hebrew and English.
10. Copy diagnostics and confirm the report contains versions, connectivity, page path, and recent event types/positions, but no episode titles, IDs, media URLs, email addresses, credentials, or browser history.

Keep this build in Internal testing until the checklist passes. Any future
Closed or Production rollout should follow the requirements shown for this
developer account in Play Console at that time.
