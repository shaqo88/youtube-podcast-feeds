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
.\build-apk.ps1 -Configuration release -Bundle -VersionCode <NEXT_CODE> -VersionName "<NEXT_VERSION>"
```

The script requires explicit release version values and rejects a release build
unless all four signing values are present. Keep two
secure, separate backups of the keystore and its passwords; losing the signing
key prevents updates for users installed with that key.

Every build removes stale APK/AAB and bundle-module intermediates before
packaging. This is intentional: interrupted builds must not contaminate the
next release candidate.

The builder uses the standard `ANDROID_HOME` and `JAVA_HOME` locations when
present, with the documented local Scoop layout as a fallback. Android-only
changes run the trusted-bridge tests and a clean, signature-verified debug APK
build on a GitHub-hosted Windows runner.

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
