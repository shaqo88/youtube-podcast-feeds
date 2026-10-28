# Search measurement: prepare catalog text once

Measured on 2026-10-28, starting from main
`e88829bae28ba79579ced872b2323d3661eef07e`. The primary checkout contained
other work; this change uses its own `ux/search-measurements-20261028` worktree.
Open PRs inspected: #105 (Pillow), #97 (Firebase), #96 and #76
(Wrangler/Undici/Miniflare), #74 (Gradle wrapper), #73 (Android plugin), and
#72 (Google identity). None changes search. No listening, artwork, queue,
service-worker, deployment, or account behavior is changed here.

## Reproduced problem and decision

Every input of at least two normalized characters scanned 7,009 episodes,
normalized the title/show/author again, split the same query for each episode,
and spread every episode into a new object before filtering. The repeated CPU
cost is measurable, even with the index already in memory. Preparing text once
and retaining the original episode records removes that work from subsequent
inputs. Only matching episodes receive a small temporary score wrapper.

This is one local optimization: the relevance weights, normalization, stable
date ordering, minimum query length, 20-result pagination, immediate input
handler, lazy shared download, and existing request-generation checks are kept.
The prepared records live in the search-page binding, so leaving and returning
prepares them again. The shared index is not mutated; library searches still
receive its original records.

## Conditions and final paired results

Headless Microsoft Edge **156.0.4314.50** on this Windows desktop; viewport
**390 × 844**; CDP **4× CPU slowdown** on the measured page. Each version ran
separately with the same index, query order, viewport, and harness. Cold index
fetch: **1.6 Mbps download, 150 ms latency**, local HTTP with gzip and no browser
HTTP cache. Warm queries use the fulfilled in-memory index promise, with
network throttling removed. Service workers and external requests are blocked
in this diagnostic server. No analytics is installed or sent.

The harness extracts each version's own scoring functions. Parsing is measured
separately with `JSON.parse` on the same payload (12 samples), rather than
mislabeling body download plus `response.json()` as parsing. CPU phases use
five rounds of nine queries (45 samples). The app's real input/render path is
also measured for five rounds of the same queries. Rendering means synchronous
markup creation, DOM replacement, and episode binding/state updates; it does
not include compositor paint or screen-reader speech. Percentiles use the
sorted sample at `floor(n * percentile)`.

| Measurement | Main | Changed |
| --- | ---: | ---: |
| Index body, decoded | 3,007,184 B | 3,007,184 B |
| Index body, gzip | 535,075 B | 535,075 B |
| Cold index transfer including reported overhead | 535,375 B | 535,375 B |
| Additional index downloads over 45 warm inputs | 0 | 0 |
| Cold index resource duration (one sample) | 3,894.7 ms | 3,035.5 ms |
| Cold input → rendered results (one sample) | 4,035.6 ms | 4,765.5 ms |
| JSON parse median / p95 | 104.3 / 231.6 ms | 109.9 / 296.0 ms |
| One-time preparation, isolated sample | included in every score pass | 889.7 ms |
| Scoring/copying median / p95 | 174.8 / 1,109.8 ms | 16.9 / 48.3 ms |
| Filtering median / p95 | 0.5 / 20.7 ms | included in scoring loop |
| Sorting median / p95 | 0.3 / 5.8 ms | 1.4 / 18.7 ms |
| Map ranked wrappers to original records, median / p95 | n/a | 0.0 / 0.2 ms |
| Warm input → rendered results, median / p95 | 795.6 / 1,632.6 ms | 115.9 / 905.5 ms |
| Rendering portion, median / p95 | 233.1 / 599.5 ms | 85.3 / 816.5 ms |

The final pair shows **85% lower median warm input-to-render time** and
**90% lower median scoring time**. The desktop had substantial scheduling and
rendering variance: an earlier diagnostic pair measured warm medians of 452.6
and 67.7 ms, and preparation of 225.3 ms. Those preliminary runs are not mixed
into the final-pair table. The rendering implementation is unchanged, so its
variation should not be treated as an independent rendering optimization.

**Cold search is not improved:** it was 730 ms slower in the final pair, and
network duration varied by 859 ms. Preparation still blocks the main thread
once. Do not interpret one cold sample as a stable regression estimate or a
speedup. This change is justified by repeated searches/typing, not download
reduction. Rendering remains a source of slow tail samples; a worker, hosted
search service, debounce, or different ranking algorithm is not justified by
this experiment.

Raw final samples: [before](results-before.json), [after](results-after.json).
Phone checks: [before](phone-before.png), [after](phone-after.png).

## Correctness and browser checks

- 61 focused Node tests pass across `search.test.mjs`, `site_assets.test.mjs`,
  and `listening.test.mjs`. The real-index compatibility test compares every
  ranked ID against the pre-change algorithm for 18 queries, including exact,
  prefix, show, author, multi-token, absent, Hebrew punctuation, niqqud, and
  spelling variants. Other tests cover relevance weights, stable date ties,
  unchanged record identity, preparation reuse, and lazy loading.
- Browser checks pass on both versions: 20 ms rapid Hebrew typing while a
  request is held shares **one** index request; clearing restores recent
  episodes and stale search completion does not replace them; following the
  actual home link while loading leaves the search page without stale results.
- HTTP 503 displays the existing Hebrew error. Editing the query after that
  failure makes a second request and restores results. Unit tests independently
  verify that the shared promise resets after failure and caches success.
- At 390 px, document width remains 390 px. Input focus is preserved while
  results update; Tab from the input reaches the first result link, with a
  visible focus indicator in the screenshots.
- The status has `role="status"` and `aria-live="polite"`; loading/failure
  messages are present. Successful search leaves it empty, so there is still
  **no successful result-count announcement**. This was reproduced on both
  versions. A real screen reader and physical phone/Android WebView were not
  tested.

Existing search limitations remain visible: niqqud is removed and straight and
Hebrew quotes are treated alike, but `ביטחון`/`בטחון`, `ווכטר`/`וועכטר`, and
unpunctuated `תשפז` are not synonym-expanded. The existing normalization removes
maqaf before punctuation replacement, so `תורה־פוד` and `תורה פוד` can differ.
The compatibility test preserves each variant's current result order rather
than silently changing relevance. A request that never resolves still has no
search-specific timeout or explicit retry button; recovery after an actual
failure still requires editing the query.

The diagnostic server supplies deterministic recent metadata derived from the
same index/catalog because latest metadata is generated as a release artifact
and is not in this Git tree. Search uses the actual committed index and page.
The transfer figures cover the index, not the preloaded shell, fonts, or covers.
These are local lab measurements, not production field metrics.

## Reproduce

Use Node and an existing Playwright installation; no application dependency or
lockfile change is needed. `SEARCH_BROWSER` is optional when Playwright's
Chromium is installed. For this Windows environment:

```powershell
$env:PLAYWRIGHT_MODULE = 'C:\Users\ShaulRoyzen\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright'
$env:SEARCH_BROWSER = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
node scripts/benchmark-search.cjs e88829bae28ba79579ced872b2323d3661eef07e
node scripts/benchmark-search.cjs working
node --test tests/search.test.mjs tests/site_assets.test.mjs tests/listening.test.mjs
```

Outputs go to ignored `.search-measurements/`. Keep the same index and browser
for comparisons; absolute times vary with host load. The benchmark injects
timing hooks only in its local HTTP response, never in the shipped bundle.
