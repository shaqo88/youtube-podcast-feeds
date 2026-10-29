# Mobile text reflow

Follow-up to merged [PR #117](https://github.com/shaqo88/youtube-podcast-feeds/pull/117), starting from main `09e87bf94cebcbbba526352faf0a33e096ff9c17`. Work was performed in a separate worktree; existing checkout edits were preserved.

## Reproduction before editing

Chromium 151.0.7922.34, CSS viewport widths **320, 360, 390**, height **844**, device scale factor **1**, Hebrew RTL and English LTR. The fixture snapshots every body descendant's computed font size and doubles each snapshot once. It does not repeatedly multiply inherited sizes. Browser zoom and viewport dimensions remain unchanged. This reproduces the text-enlargement method in #117, rather than simulating Android system settings.

All six doubled-text baseline cases confirmed crowded/clipped header controls, bottom-navigation labels outside their targets, and overlap between the mini-player and navigation. These obscure destinations and make playback/navigation difficult to operate. See [baseline measurements](before-matrix.json).

| Language / width | Before, doubled text | After, doubled text |
| --- | --- | --- |
| Hebrew / 320 | [Screenshot](before-he-320-home-2x.png) | [Screenshot](after-he-320-home-2x.png) |
| Hebrew / 360 | [Screenshot](before-he-360-home-2x.png) | [Screenshot](after-he-360-home-2x.png) |
| Hebrew / 390 | [Screenshot](before-he-390-home-2x.png) | [Screenshot](after-he-390-home-2x.png) |
| English / 320 | [Screenshot](before-en-320-home-2x.png) | [Screenshot](after-en-320-home-2x.png) |
| English / 360 | [Screenshot](before-en-360-home-2x.png) | [Screenshot](after-en-360-home-2x.png) |
| English / 390 | [Screenshot](before-en-390-home-2x.png) | [Screenshot](after-en-390-home-2x.png) |

## Coherent fix

Mobile header and navigation can wrap. Measured header, navigation and compact-player heights determine content reserves, mini-player placement, scroll padding and menu bounds. Measurements use the existing same-origin stylesheet's CSSOM, retaining the production CSP. A container query gives enlarged mini-player text separate seek/time rows. Normal text retains the single navigation row and existing mini-player arrangement.

Long titles wrap in a bounded, scrollable title region, keeping playback controls available. Arrow Up/Down, Page Up/Down, Home and End scroll an overflowing title; Enter and Space retain button activation. Expanded speed/Stop buttons grow with their labels. Focused page controls are brought into the unobscured interval. Touch controls retain at least 44 CSS pixels in the tested conditions.

When fixed chrome would leave less than 96 CSS pixels for content, the same navigation and player nodes move into document flow before main content. This preserves the window scroller and media nodes, with state-preserving DOM movement where supported and focus restoration in the fallback. They return to their original positions when space is available. Menus scroll within viewport bounds; episode entrance/lazy-render containment is disabled only where necessary for menu placement and reliable enlarged-text focus scrolling.

No feeds, metadata, routes, stored progress, account/storage logic or media commands were changed.

## Validation and what it establishes

See [complete measurements](after-matrix.json) and the runnable optional browser regression [source](../../../tests/text-reflow.browser.mjs).

| Method | Exact settings | Establishes |
| --- | --- | --- |
| Text enlargement | 320/360/390 × 844 CSS px; HE/EN; 1× and 2× computed text; DPR 1; unchanged zoom | 60 cases: Home, Search, show, queue and expanded player. Text/control bounds, no horizontal page overflow, dock separation, focus visibility, target dimensions and hit testing. |
| Short viewport | 320×568, 360×640, 390×640; HE/EN; 1×/2× text | 12 further Home/player cases; reachable controls and document-flow fallback, including navigation Tab order. |
| Persistent CSSOM text fixture | HE/EN; doubled absolute/rem/vw font declarations; production CSP; normal entrance motion | Newly rendered menus/routes inherit enlarged text; bounded popovers and live resize 390×844 → 320×568 → 390×844 switch flow on/off without resetting doubled navigation text. |
| Viewport resize | Same CSS text fixture; dimensions above | Responsive rearrangement at changed available space. Resizing itself does not enlarge text. |
| Pinch-style visual zoom | CDP page-scale factor 1 → 2; layout width 390, DPR 1 | Visual width 390 → 195; layout width remains 390 and navigation font remains 11 px. This is visual magnification, not text enlargement or desktop browser UI zoom. |
| SPA Back | HE/EN; saved scroll offset 500 | Back returns to offset 500; layout focus handling does not override route restoration. |

The browser suite contains 72 layout cases and 17 additional experiments. All pass. Screenshots were manually inspected, including long Hebrew titles, English player controls, wrapped navigation and short-screen flow. The longest actual catalog title (645 UTF-16 code units, Hebrew) is substituted into the rendered player after actual fixture playback starts and pauses. Complete text remains accessible by scrolling; no ellipsis or text-size reduction is introduced.

Additional evidence: [Search](after-en-360-search-2x.png), [show](after-he-320-show-2x.png), [queue](after-he-390-queue-2x.png), [player](after-en-320-player-2x.png), [focused lower player controls](after-en-320-player-2x-controls.png), [short-screen Hebrew](after-he-320x568-home-2x.png), [short-screen English](after-en-320x568-home-2x.png), [normal Hebrew](after-he-390-home-1x.png), [normal English](after-en-390-home-1x.png).

Regression checks:

- `npm test`: 112 passed, including dock measurement/deduplication, hidden/expanded-player reserves, title reading keys and preserved activation keys.
- Python `unittest`: 32 passed across `test_site_helpers`, `test_stable_generated_output`, `test_android_wrapper_source`, `test_android_resources`.
- Android bridge policy: 20 checks passed.
- Local feed validation passed; no network validation or production writes.
- Retained-snapshot release render; [generated-output audit](generated-audit.json) compares every tracked public file against main, allowing only HTML asset/build stamps, assembled CSS/JS and the service-worker cache fingerprint. Feeds and metadata remain unchanged.

Browser command (Playwright and Chromium are external optional test prerequisites):

```text
node tests/text-reflow.browser.mjs --PLAYWRIGHT_MODULE=<absolute-playwright-module> --CHROMIUM_EXECUTABLE=<absolute-chromium-executable>
```

`--REFLOW_BASELINE=1` captures six baseline Home cases when run against the baseline revision. All requests use intercepted local fixtures and fresh guest browser contexts. Media uses a silent WAV fixture; external requests are aborted. No signed-in account data is used.

## Limitations

This is Chromium browser layout/keyboard validation. No physical Android system-font scaling, Android IME, TalkBack, other screen reader, desktop browser UI/default zoom, Safari or Firefox acceptance was performed. Browser text enlargement and the separate pinch probe do not establish Android system-font-scaling acceptance. The local WAV establishes layout with an active/paused player, not production-media/network seeking acceptance. The English UI uses the catalog's real Hebrew long title as a deliberate mixed-direction stress case. Very long titles require scrolling inside their title region; the short-screen arrangement requires document scrolling to return to navigation/player.
