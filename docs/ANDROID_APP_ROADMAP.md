# Android App Roadmap

## Current State

- The Android app is a WebView wrapper for `https://torah-pod.pages.dev/`.
- Playback uses HTML audio in the WebView.
- Android native `MediaPlayer` playback is disabled by default and remains a
  developer-only experiment.
- Android notifications mirror the active HTML audio session and route
  play/pause/stop commands back to the WebView.
- Startup and refresh have native loading indicators.

## Stability Baseline

Before adding larger native features, keep these flows green:

1. Cold app launch.
2. First episode play after launch.
3. Switch episodes while audio is playing.
4. Queue item playback.
5. Bottom player pause/resume.
6. Android notification pause/resume.
7. Pull-to-refresh.
8. Service worker cache update after deploy.

## Next Stages

### Stage 1: Stabilize WebView Shell

- Keep HTML audio as the primary playback engine.
- Keep native notification mirroring only; do not re-enable native
  `MediaPlayer` by default.
- Improve startup, refresh, and offline/error states.
- Use `window.TorahPodPlaybackDebug()` for playback timing diagnostics.

### Stage 2: App-Like Navigation

- Add a native or web-level back/close policy for drawers and expanded player.
- Verify deep links to podcast pages and episode anchors.
- Improve behavior when Android restores the activity from the background.
- Add a clear empty/error state when the start URL cannot load.

### Stage 3: Installable Release Hygiene

- Decide package name, version code, version name, and release signing flow.
- Replace debug signing with a release keystore.
- Add a repeatable install/update checklist.
- Confirm notification permission and Android System WebView requirements.

### Stage 4: Native Audio Re-Evaluation

Only revisit native `MediaPlayer` after the HTML-audio app is stable.

- Keep native audio behind `localStorage.torahpod-native-audio-enabled`.
- Add Android-side logs for service start, prepare, error, completion, and
  release events.
- Test replacement between episodes before enabling for users.
- Prefer deleting the native playback path if notification mirroring fully
  satisfies the app requirements.

## Current Recommendation

Treat the app as a stable WebView-based native shell with HTML playback and
native notification integration. Continue improving native app feel around
startup, navigation, refresh, offline states, and release packaging before
returning to native audio playback.
