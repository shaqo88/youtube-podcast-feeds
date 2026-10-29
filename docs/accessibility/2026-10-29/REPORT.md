# Accessibility and interaction review — 29 October 2026

Baseline: `3a912959e71f00d3cfdd3b1b9e995e01182698e2` (current main when the review began).
Work was isolated on `fix/interaction-accessibility-20261029`. The original
checkout's three modified files and two untracked paths were preserved.
Reviewed repository guidance, current source, recent listening/search/account
merges (#106, #108, #114–116), and the seven open dependency PRs. None overlapped.

## Confirmed problems and fixes

1. **Queue editing loses keyboard focus.** Add three episodes from Home, open
   Queue, focus the first episode's Down button and press Enter. The order
   changes, but `document.activeElement` becomes `BODY`. Removing a row has the
   same cause: every render replaces the row DOM. Repeated keyboard editing
   therefore requires finding the controls again. A focusable drag handle also
   claims to be a button while providing no keyboard action.

   Restore the same episode/action after rendering, use another enabled action
   at an ordering boundary, and use the next/previous row after removal. When
   the final row disappears, focus the empty-state text. Label each action
   group with its episode title, and expose the existing Up/Down buttons as
   the keyboard alternative to pointer dragging. Announce explicit moves,
   removals and clearing through a persistent, visually hidden status region;
   ordinary renders and playback ticks do not announce queue state. This
   separate region leaves playback errors and Retry controls intact.

2. **Escape navigates instead of closing episode menus.** Visit Queue, then
   Home; open an episode's More menu, focus Save, and press Escape. The menu
   remains open until route navigation removes it; the browser returns to
   Queue. Escape with no overlay also consumes browser history. Header-menu
   dismissal can leave focus inside hidden content.

   Dismiss the episode menu and focus its summary. Restore the header trigger
   when dismissing its menu. Escape handles overlays only. The native Back
   entry point still navigates when no overlay is open, and expanded playback
   takes precedence over an episode menu behind it.

3. **Artwork navigation links are unnamed.** On Search/Explore, inspect or tab
   to a podcast cover. The anchor contains an image with `alt=""`; the adjacent
   title is a separate link and supplies no name to the artwork anchor. Axe
   reports `link-name`, and DOM inspection confirms the missing name. Assign
   the containing podcast's title to the artwork link during accessibility
   setup, including page navigation. Appearance and destinations are unchanged.

## Evidence

- [Before queue edit](before-queue.png) / [after queue edit](after-queue.png).
- [Before Escape](before-menu-escape.png) / [after Escape](after-menu-escape.png).
- [Phone text enlarged to 200%](after-phone-200-percent.png).
- [Baseline interaction trace](before-interactions.json) and
  [updated interaction trace and axe results](after-interactions.json).

Artwork naming is an accessibility-tree/DOM change with no visible difference;
the browser regression checks every artwork link against its podcast title.

## Verification

- `npm test`: 110 passed, including account isolation, history, listening,
  search/generated-bundle consistency and onboarding. Miniflare requires local
  networking; the sandbox-only run could not connect to its loopback endpoint.
- Python: 32 passed across `test_site_helpers`, `test_stable_generated_output`,
  `test_android_wrapper_source`, and `test_android_resources`.
- Android bridge policy: 20 checks passed.
- Browser regression: `node tests/accessibility.browser.mjs`. Supply
  `PLAYWRIGHT_MODULE`, `CHROMIUM_EXECUTABLE`, and optionally `AXE_SCRIPT` when
  using an external runtime. Screenshots/traces are written to
  `tmp/accessibility/`. No additional production dependency is introduced.
- Chromium at 390 × 844 and 1280 × 800: queue move/removal and ordering
  boundaries, focus restoration, menus, page navigation/Back, HTML playback,
  pause, playback speed, expanded-player keyboard containment, Hebrew RTL and
  English LTR. Artwork links are checked after page navigation and reload.
- Axe-core 4.10.3: no violations on the settled Hebrew phone queue, Hebrew
  phone search/player, Hebrew desktop search, and English desktop search.
  Entrance-animation contrast reports were manually traced to temporary
  opacity and disappeared after settling/reduced motion. The phone scans'
  contrast results include incomplete items; this is not a full contrast audit.
- A manually aborted media request exposed a polite playback-error status and
  a Retry button. Repeated playback ticks did not mutate the app status region.
- Generated shared JavaScript and service-worker revision were refreshed using
  the repository generator. No catalog, routes, feeds or stored-progress format
  changes, and no full source synchronization or production configuration change.

## Limits

No screen reader, physical Android device, emulator, or native audio service
acceptance was performed. Android user-agent/bridge checks use a stub in
Chromium. Authentication/account data were not changed; account behavior is
covered by the existing tests. Browser media uses a local silent WAV fixture.
The seek slider's keyboard input was exercised, but the intercepted fixture's
media-position result was inconsistent and is recorded in the trace rather
than counted as verified real-media seeking. Existing seek-handler tests pass;
real-media seeking still needs device/browser acceptance. Text enlargement is
a browser fixture that doubles computed text sizes, not Android system font
scaling; overflow checks and screenshots do not constitute acceptance of every
control at every font scale. At doubled text size, the fixed phone header and
bottom navigation still show crowded/clipped content despite no horizontal
document overflow. That remains outside the three selected fixes. The broad
Python discovery run was interrupted;
the focused checks above are the completed Python verification.
