# App Playback QA

Current architecture:

- Web and Android app playback use HTML audio as the primary engine.
- Android native audio is disabled by default and should be treated as
  experimental.
- Android notification controls mirror the active HTML audio session.
- Service worker cache version changes should be verified after playback UI
  changes.
- Native app roadmap and staging are tracked in
  `docs/ANDROID_APP_ROADMAP.md`.

Manual test checklist:

1. Launch the Android app cold, wait for the page to settle, then tap Listen on
   an episode.
2. Confirm the bottom player appears with the selected episode title and the
   episode starts playing.
3. While the first episode is playing, navigate to another podcast page and tap
   Listen on a different episode.
4. Confirm the bottom player title changes to the new episode and audio starts
   for that episode without crashing.
5. Add two episodes to the queue, open the queue, and tap the play button on an
   item.
6. Confirm queue playback starts or switches to the selected queued episode.
7. Pause and resume from the bottom player.
8. Pause and resume from the Android notification.
9. Close the bottom player and confirm the notification is removed.
10. Pull to refresh in the Android app and confirm the app reloads without
    breaking playback controls.

Regression notes:

- If tapping Listen does nothing for several seconds, check whether the active
  service worker version matches the latest `public/sw.js` cache name.
- To inspect recent playback lifecycle events, run
  `window.TorahPodPlaybackDebug()` from the WebView/browser console.
- If web playback works but Android app playback does not, keep native audio
  disabled and inspect the WebView HTML audio path first.
- If notification controls disappear while playback works, inspect the native
  notification mirror bridge rather than the audio engine.
