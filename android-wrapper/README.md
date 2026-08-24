# Torah Pod Android Wrapper

Minimal Android WebView client for <https://torah-pod.pages.dev/>. HTML audio
is the primary playback engine; Android code provides the application shell and
media-notification integration.

Build and install a local debug APK:

```powershell
.\build-apk.ps1
.\install-apk.ps1
```

The build output is `android-wrapper\build\torah-pod-debug.apk`. Android
System WebView is required on the target device. The launch screen displays the
installed version name and code, so testers can confirm which build is running.
If Android terminates the WebView renderer, the wrapper removes the dead view
and recreates the activity instead of leaving an unresponsive screen.

## Release candidates

The debug APK is intentionally signed with a disposable debug key. It is for
local installs only and must never be uploaded to Google Play.

To create a production-signed APK, create and back up a release keystore
outside this repository. Then set these environment variables for the current
PowerShell session (never commit the values or the keystore):

```powershell
$env:TORAH_POD_RELEASE_KEYSTORE = "C:\secure\torah-pod-release.jks"
$env:TORAH_POD_RELEASE_KEY_ALIAS = "torah-pod"
$env:TORAH_POD_RELEASE_KEYSTORE_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host "Keystore password" -AsSecureString)).Password
$env:TORAH_POD_RELEASE_KEY_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host "Key password" -AsSecureString)).Password
.\build-apk.ps1 -Configuration release -Bundle
```

All builds read their identity from `release-version.json`. A release build
rejects explicitly supplied values that do not match that file, and requires
all four signing values. Keep two
secure, separate backups of the keystore and its passwords; losing the signing
key prevents updates for users installed with that key.

After Play has accepted the current version code, prepare the next candidate
with one deliberate source-controlled increment:

```powershell
.\set-release-version.ps1 -Bump patch
```

This advances both the semantic version and Android version code. Use
`-Bump minor`, `-Bump major`, or explicit `-VersionName`/`-VersionCode` only
when the product change warrants it. Review and commit the JSON change before
building; CI never mutates versions automatically.

Every build removes stale APK/AAB and bundle-module intermediates before
packaging. This is intentional: interrupted builds must not contaminate the
next release candidate.

The builder uses the standard `ANDROID_HOME` and `JAVA_HOME` locations when
present, with the documented local Scoop layout as a fallback. Android-only
changes run the trusted-bridge tests and a clean, signature-verified debug APK
build on a GitHub-hosted Windows runner.

The manually dispatched **Build Android Release Candidate** workflow builds a
signed APK/AAB only after approval of the `google-play-release` GitHub
environment. It reads protected signing secrets, deletes the temporary
keystore in `finally`, verifies pinned bundletool, and retains the artifacts
with hashes and source provenance for 30 days. It does not publish to Google
Play. Configure Play API publishing only after the app exists in Play Console
and a least-privilege service account has been created.

The **Prepare and publish Android to Google Play** workflow prepares a signed
AAB automatically for Android-related changes on `main`. Its publishing job
targets only the Play **internal** track and is protected by the
`google-play-internal` GitHub environment, so GitHub pauses for a required
reviewer before every upload. No Play upload occurs without that approval.
Configure these environment secrets there:

```text
ANDROID_RELEASE_KEYSTORE_BASE64
TORAH_POD_RELEASE_KEY_ALIAS
TORAH_POD_RELEASE_KEYSTORE_PASSWORD
TORAH_POD_RELEASE_KEY_PASSWORD
GOOGLE_SERVICE_ACCOUNT_JSON
```

Add yourself as a required reviewer for `google-play-internal`. Keep
production promotion as a deliberate Play Console step until the store
listing, data-safety declaration, and tester requirements are complete. The
existing **Build Android Release Candidate** workflow remains available when
you want an artifact without publishing it.

With the official `bundletool-all` JAR available locally (or pointed to by
`BUNDLETOOL_JAR`), add `-Bundle` to produce a signed Android App Bundle for
Google Play:

The bundle is signed, verified with `jarsigner`, and structurally validated by
bundletool before the build reports success. The APK is verified with Android's
APK signature verifier.

To install a signed release candidate on a test device after building it:

```powershell
.\install-apk.ps1 -Configuration release
```

Release planning, signing, architecture decisions, and regression checklists
are maintained only in the private operations repository.

Android backup and device-transfer extraction are disabled because WebView
storage can contain listening history. Web contents debugging is disabled in
all packaged builds, file/content access is blocked, mixed content is rejected,
and Safe Browsing is explicitly enabled on supported Android versions.
