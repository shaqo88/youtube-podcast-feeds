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

Playback architecture:

- HTML audio in the WebView is the primary playback engine.
- Native `MediaPlayer` playback is disabled by default because replacement
  between episodes was unstable on Android. It is available only as a developer
  opt-in with `localStorage.torahpod-native-audio-enabled = "true"`.
- The Android service mirrors WebView HTML playback into a foreground media
  notification. Notification play/pause/stop commands are sent back into the
  WebView player.
- The web player remains the browsing, queue, progress, and resume UI.

Current APK path:

```text
android-wrapper\build\torah-pod-debug.apk
```
