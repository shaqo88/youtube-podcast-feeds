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

Release planning, signing, architecture decisions, and regression checklists
are maintained only in the private operations repository.
