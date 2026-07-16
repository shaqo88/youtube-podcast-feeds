# Torah Pod Android Wrapper

This is a minimal Android WebView wrapper for `https://torah-pod.pages.dev/`.

Build:

```powershell
.\build-apk.ps1
```

Output:

```text
android-wrapper\build\torah-pod-debug.apk
```

Install with USB debugging:

```powershell
.\install-apk.ps1
```

This wrapper does not require Chrome, but it does rely on Android System WebView being present on the device.

Native audio:

- Episode playback is handed from the WebView to a native foreground media service when the app detects the Android bridge.
- The native service owns background playback and the Android notification play/pause control.
- The web player remains the browsing/queue UI; native progress sync is intentionally minimal in this first prototype.

Current APK path:

```text
android-wrapper\build\torah-pod-debug.apk
```
