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
System WebView is required on the target device.

## Release candidates

The debug APK is intentionally signed with a disposable debug key. It is for
local installs only and must never be uploaded to Google Play.

To create a production-signed APK, create and back up a release keystore
outside this repository. Then set these environment variables for the current
PowerShell session (never commit the values or the keystore):

```powershell
$env:TORAH_POD_RELEASE_KEYSTORE = "C:\secure\torah-pod-release.jks"
$env:TORAH_POD_RELEASE_KEYSTORE_PASSWORD = "..."
$env:TORAH_POD_RELEASE_KEY_ALIAS = "torah-pod"
$env:TORAH_POD_RELEASE_KEY_PASSWORD = "..."
.\build-apk.ps1 -Configuration release -VersionCode 2 -VersionName "0.2.0"
```

The script rejects a release build unless all four values are present. Keep two
secure, separate backups of the keystore and its passwords; losing the signing
key prevents updates for users installed with that key. Before a Play release,
we will also add an Android App Bundle (`.aab`) build and complete the store
listing and policy checklist.

With the official `bundletool-all` JAR available locally (or pointed to by
`BUNDLETOOL_JAR`), add `-Bundle` to produce a signed Android App Bundle for
Google Play:

```powershell
.\build-apk.ps1 -Configuration release -VersionCode 2 -VersionName "0.2.0" -Bundle
```

To install a signed release candidate on a test device after building it:

```powershell
.\install-apk.ps1 -Configuration release
```

Release planning, signing, architecture decisions, and regression checklists
are maintained only in the private operations repository.
