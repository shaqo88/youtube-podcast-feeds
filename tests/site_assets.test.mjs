import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync("public/assets/app.js", "utf8");
const worker = readFileSync("public/sw.js", "utf8");
const headers = readFileSync("public/_headers", "utf8");
const source = readFileSync("podcast_feeds/site.py", "utf8");
const css = readFileSync("public/assets/site.css", "utf8");

test("player bundle contains current controls and readiness handoff", () => {
  assert.match(app, /playerVolume/);
  assert.match(app, /nativePrompt\("ready"\)/);
  assert.doesNotMatch(app, /playerSleep|sleepTimer|Set a sleep timer/);
});

test("player controls remain localized after a language change", () => {
  for (const content of [app, source]) {
    assert.match(content, /playerSeek\?\.setAttribute\("aria-label", t\("player_progress"\)\)/);
    assert.match(content, /playerVolume\.setAttribute\("aria-label", t\("volume"\)\)/);
  }
});

test("navigation and player landmarks follow the selected language", () => {
  assert.match(app, /document\.querySelectorAll\("\[data-i18n-aria\]"\)/);
  assert.match(app, /\[document\.querySelector\("\.nav"\), "primary_navigation"\]/);
  assert.match(app, /\[player, "audio_player"\]/);
  assert.match(source, /data-i18n-aria="primary_navigation"/);
  assert.match(source, /data-i18n-aria="app_navigation"/);
  assert.match(source, /data-i18n-aria="audio_player"/);
  assert.match(source, /"audio_player": "נגן שמע"/);
  assert.match(source, /"audio_player": "Audio player"/);
});

test("the seek control exposes its current playback position", () => {
  for (const content of [app, source]) {
    assert.match(content, /playerSeek\.setAttribute\("aria-valuetext", `\$\{formatTime\(position\)\} \/ \$\{formatTime\(duration\)\}`\)/);
    assert.match(content, /playerSeek\.setAttribute\("aria-valuetext", `\$\{formatTime\(position\)\} \/ \$\{duration \? formatTime\(duration\) : "--"\}`\)/);
  }
});

test("the volume control announces and preserves its current level", () => {
  for (const content of [app, source]) {
    assert.match(content, /function updateVolumeControl\(volume = playbackVolume\(\)\)/);
    assert.match(content, /playerVolume\.setAttribute\("aria-valuetext", `\$\{Math\.round\(normalized \* 100\)\}%`\)/);
    assert.match(content, /updateVolumeControl\(volume\)/);
  }
  for (const content of [css, source]) {
    assert.match(content, /\.player-volume:focus/);
  }
});

test("generated asset source retains current player behavior", () => {
  assert.match(source, /playerVolume/);
  assert.match(source, /nativePrompt\("ready"\)/);
  assert.doesNotMatch(source, /playerSleep|sleepTimer|Set a sleep timer/);
});

test("service worker refreshes scripts and styles from network first", () => {
  assert.match(worker, /request\.destination === "script"/);
  assert.match(worker, /request\.destination === "style"/);
  const networkFirst = worker.indexOf('request.destination === "script"');
  const genericCacheFirst = worker.lastIndexOf("caches.match(request)");
  assert.ok(networkFirst >= 0 && networkFirst < genericCacheFirst);
});

test("service worker refreshes catalog and feed data with offline fallback", () => {
  assert.match(worker, /url\.pathname\.endsWith\("\.json"\)/);
  assert.match(worker, /url\.pathname\.endsWith\("\.xml"\)/);
  assert.match(worker, /const freshData/);
  assert.match(worker, /"\.\/catalog\.json"/);
  assert.match(worker, /"\.\/catalog-meta\.json"/);
  assert.match(worker, /"\.\/status\.json"/);
  assert.match(source, /shell_fingerprint_paths/);
  assert.match(source, /_write_security_headers\(\)\s+_write_pwa_assets\(\)/);
});

test("accessibility bootstrap repairs legacy pages and preserves navigation context", () => {
  for (const content of [app, source]) {
    assert.match(content, /setupAccessibility\(\)/);
    assert.match(content, /skip_to_content/);
    assert.match(content, /detailsButton\.dataset\.playerDetails/);
    assert.match(content, /aria-modal/);
    assert.match(content, /restoreFocus/);
    assert.match(content, /navigation_failed/);
    assert.match(content, /showUpdateNotice\(\)/);
    assert.match(content, /controllerchange/);
    assert.match(content, /document\.querySelector\("main"\)\?\.focus/);
  }
  assert.doesNotMatch(app, /catch \{\s*location\.href = url\.href/);
});

test("the full player keeps keyboard focus contained", () => {
  for (const content of [app, source]) {
    assert.match(content, /const focusRoot = player\?\.classList\.contains\("is-expanded"\) \? player : openDrawer/);
    assert.match(content, /event\.key === "Tab" && focusRoot/);
    assert.match(content, /node\.getClientRects\(\)\.length > 0/);
    assert.match(content, /event\.shiftKey && document\.activeElement === first/);
    assert.match(content, /document\.activeElement === last/);
  }
});

test("the redesign exposes four destination routes and replaces drawers", () => {
  const home = readFileSync("public/index.html", "utf8");
  for (const route of ["/", "/subscriptions/", "/search/", "/queue/"]) {
    assert.match(home, new RegExp(`data-nav-route="${route.replaceAll("/", "\\/")}"`));
  }
  assert.doesNotMatch(home, /data-library-drawer|data-queue-drawer/);
  assert.match(source, /function updateDestinationNavigation\(\)/);
  assert.match(css, /@media \(min-width: 901px\)[\s\S]*\.app-bottom-nav/);
});

test("catalog search is lazy, ranked, bounded, and privacy-safe", () => {
  for (const content of [app, source]) {
    assert.match(content, /function searchScore\(query, title, show, author\)/);
    assert.match(content, /if \(query\.length < 2\)/);
    assert.match(content, /episodeLimit = 30/);
    assert.match(content, /searchIndexPromise = fetch\(url\.href\)/);
    assert.match(content, /payload\?\.schema_version !== 1/);
  }
  const index = JSON.parse(readFileSync("public/search-index.json", "utf8"));
  assert.equal(index.schema_version, 1);
  assert.ok(index.episodes.length > 0);
  assert.deepEqual(Object.keys(index.episodes[0]).sort(), ["audio_url", "duration", "id", "page_url", "published", "show_slug", "title"]);
  assert.doesNotMatch(JSON.stringify(index.episodes[0]), /description|email/i);
  const shell = worker.slice(worker.indexOf("const SHELL_ASSETS"), worker.indexOf("];", worker.indexOf("const SHELL_ASSETS")));
  assert.doesNotMatch(shell, /search-index\.json/);
});

test("subscription visits migrate once and calculate capped new counts", () => {
  for (const content of [app, source]) {
    assert.match(content, /const showVisitsKey = "torahpod:v1:show-visits"/);
    assert.match(content, /const uxMigrationKey = "torahpod:v1:ux-0\.4\.0-migrated"/);
    assert.match(content, /function migrateShowVisits\(\)/);
    assert.match(content, /function newEpisodeCount\(card\)/);
    assert.match(content, /count > 99 \? "99\+"/);
    assert.match(content, /visits\[state\.slug\] = Date\.now\(\)/);
  }
});

test("mini player expands into a swipeable modal sheet and restores focus", () => {
  for (const content of [app, source]) {
    assert.match(content, /player\.setAttribute\("role", "dialog"\)/);
    assert.match(content, /player\.setAttribute\("aria-modal", "true"\)/);
    assert.match(content, /playerExpandedTrigger\?\.isConnected\) playerExpandedTrigger\.focus/);
    assert.match(content, /delta < -60/);
    assert.match(content, /delta > 80/);
    assert.match(content, /if \(player\?\.classList\.contains\("is-expanded"\)\) setPlayerExpanded\(false\)/);
  }
});

test("onboarding accessibility labels follow the selected language", () => {
  assert.match(source, /data-i18n-aria="onboarding_steps"/);
  assert.match(source, /"onboarding_steps": "שלבי צירוף פודקאסט"/);
  assert.match(source, /"onboarding_steps": "Podcast onboarding steps"/);
});

test("in-place navigation rejects invalid responses and only the newest request may render", () => {
  for (const content of [app, source]) {
    assert.match(content, /new AbortController\(\)/);
    assert.match(content, /navigationController\?\.abort\(\)/);
    assert.match(content, /signal: controller\.signal/);
    assert.match(content, /response\.headers\.get\("content-type"\)/);
    assert.match(content, /contentType\.includes\("text\/html"\)/);
    assert.match(content, /requestId !== navigationRequestId/);
    assert.match(content, /error\?\.name === "AbortError"/);
    assert.match(content, /if \(requestId === navigationRequestId\)/);
    assert.match(content, /navigationTimeoutMs = 30000/);
    assert.match(content, /navigationTimedOut = true/);
    assert.match(content, /window\.clearTimeout\(navigationTimeout\)/);
    assert.match(content, /error\?\.name === "AbortError" && !navigationTimedOut/);
    assert.match(content, /function showNavigationFailure\(url, push\)/);
    assert.match(content, /retry\.textContent = t\("navigation_retry"\)/);
    assert.match(content, /navigateTo\(url, \{ push \}\)/);
    assert.match(content, /showNavigationFailure\(url\.href, push\)/);
  }
});

test("in-place navigation does not retain stale list event listeners", () => {
  for (const content of [app, source]) {
    assert.match(content, /listBindingsAbortController\?\.abort\(\)/);
    assert.match(content, /listBindingsAbortController = new AbortController\(\)/);
    assert.match(content, /\{ signal: listBindingSignal \}/);
  }
});

test("future generated pages avoid nested interactive player controls", () => {
  assert.match(source, /class=\"skip-link\" href=\"#main-content\"/);
  assert.match(source, /<main id=\"main-content\" tabindex=\"-1\">/);
  assert.match(source, /class=\"player-details\" type=\"button\" data-player-details/);
  assert.doesNotMatch(source, /class=\"player-main\" role=\"button\"/);
});

test("Hebrew search normalizes diacritics and common punctuation", () => {
  for (const content of [app, source]) {
    assert.match(content, /function normalizeSearchText\(value\)/);
    assert.match(content, /\\u0591-\\u05C7/);
    assert.match(content, /normalizeSearchText\(item\.dataset\.searchItem\)\.includes\(term\)/);
  }
});

test("searches explain when their filters produce no results", () => {
  for (const content of [app, source]) {
    assert.match(content, /className = "list-empty-state"/);
    assert.match(content, /emptyState\.textContent = t\("no_search_results"\)/);
  }
});

test("show pages offer accessible RSS link copying", () => {
  for (const content of [app, source]) {
    assert.match(content, /function setupFeedCopyButtons\(\)/);
    assert.match(content, /data-copy-feed/);
    assert.match(content, /navigator\.clipboard\.writeText/);
    assert.match(content, /announceAppStatus\(t\("feed_copied"\)\)/);
  }
});

test("episodes offer native sharing with a clipboard fallback", () => {
  for (const content of [app, source]) {
    assert.match(content, /data-share-episode/);
    assert.match(content, /function shareEpisode\(article\)/);
    assert.match(content, /navigator\.share\(payload\)/);
    assert.match(content, /navigator\.clipboard\.writeText\(url\)/);
    assert.match(content, /function episodeShareUrl\(article\)/);
    assert.match(content, /replace\(\/-library-recent\$\/, ""\)/);
  }
});

test("Android notification seek actions reach browser-based playback", () => {
  for (const content of [app, source]) {
    assert.match(content, /command === "seekBy"/);
    assert.match(content, /Number\(payload\?\.seconds\)/);
    assert.match(content, /activeAudio\.currentTime = Math\.max\(0/);
  }
});

test("HTML playback failures offer localized retries without accepting stale events", () => {
  for (const content of [app, source]) {
    assert.match(content, /playbackStartupTimeoutMs = 30000/);
    assert.match(content, /function isCurrentPlaybackAttempt\(audio, attemptId\)/);
    assert.match(content, /activeAudio === audio/);
    assert.match(content, /playbackAttemptId === attemptId/);
    assert.match(content, /audio\.addEventListener\("error"/);
    assert.match(content, /\.catch\(\(\) => failPlaybackAttempt/);
    assert.match(content, /failPlaybackAttempt\(audio, state, article, retry, "stalled"/);
    assert.match(content, /saveCurrentProgress\(audio, article\)/);
    assert.match(content, /saveCurrentStateProgress\(audio, state\)/);
    assert.match(content, /button\.dataset\.i18n = "playback_retry"/);
    assert.match(content, /function resumeHtmlPlayback\(\)/);
  }
});

test("About diagnostics expose only a privacy-safe playback projection", () => {
  for (const content of [app, source]) {
    assert.match(content, /function diagnosticsReport\(\)/);
    assert.match(content, /safeArray\(playbackDebugKey\)\.slice\(-20\)/);
    assert.match(content, /appVersion: appMatch \? appMatch\[1\] : "web"/);
    assert.match(content, /siteVersion/);
    assert.match(content, /online: navigator\.onLine !== false/);
    assert.match(content, /page: location\.pathname/);
    assert.match(content, /type: \/\^\[a-z0-9-\]/);
    assert.match(content, /position: Number\.isFinite\(rawPosition\)/);
    assert.match(content, /data-copy-diagnostics/);

    const diagnosticsStart = content.indexOf("function diagnosticsReport()");
    const diagnosticsEnd = content.indexOf("async function copyDiagnostics()", diagnosticsStart);
    const reportBody = content.slice(diagnosticsStart, diagnosticsEnd);
    assert.doesNotMatch(reportBody, /event\?\.(id|title|page|src|url|email)/);
    assert.doesNotMatch(reportBody, /location\.(href|search|hash)/);
    assert.doesNotMatch(reportBody, /document\.cookie|localStorage\./);
  }
});

test("shared episode links visibly identify their target", () => {
  for (const content of [app, source]) {
    assert.match(content, /function hashTarget\(hash = location\.hash\)/);
    assert.match(content, /decodeURIComponent\(hash\.slice\(1\)\)/);
    assert.match(content, /document\.getElementById\(fragment\)/);
    assert.match(content, /function highlightSharedEpisode\(\)/);
    assert.match(content, /article\.classList\.add\("is-deep-linked"\)/);
  }
  for (const content of [css, source]) {
    assert.match(content, /\.episode\.is-deep-linked/);
  }
});

test("queue supports autoplay handoff, touch reorder, links, and navigation cleanup", () => {
  for (const content of [app, source]) {
    assert.match(content, /command === "ended"/);
    assert.match(content, /function bindQueueDrag\(list\)/);
    assert.match(content, /data-queue-drag-handle/);
    assert.match(content, /queue-meta/);
    assert.match(content, /history\.back\(\)/);
    assert.match(content, /function setupHomeNavButton\(\)/);
    assert.match(content, /appStatus\.hidden = true/);
    assert.match(content, /const currentIndex = entries\.findIndex\(\(item\) => item\.id === currentId\)/);
    assert.match(content, /if \(currentIndex < 0\) return/);
    assert.doesNotMatch(content, /link\.textContent = `⌂ \$\{t\("home"\)\}`/);
  }
});

test("marking an episode unplayed clears completed listening state", () => {
  for (const content of [app, source]) {
    assert.match(content, /if \(!played\) \{/);
    assert.match(content, /progress\?\.completed\) safeRemove\(progressKey\(state\.id\)\)/);
    assert.match(content, /last\?\.id === state\.id && last\.completed\) safeRemove\(lastKey\)/);
    assert.match(content, /updateEpisodeProgress\(article\)/);
  }
});

test("production headers block inline injection and isolate the app safely", () => {
  for (const content of [headers, source]) {
    assert.doesNotMatch(content, /unsafe-inline/);
    assert.match(content, /script-src-attr 'none'/);
    assert.match(content, /style-src 'self'; style-src-attr 'none'/);
    assert.match(content, /Strict-Transport-Security: max-age=31536000/);
    assert.match(content, /X-Frame-Options: DENY/);
    assert.match(content, /X-Permitted-Cross-Domain-Policies: none/);
    assert.match(content, /Cross-Origin-Opener-Policy: same-origin/);
    assert.match(content, /Cross-Origin-Resource-Policy: same-site/);
    assert.match(content, /Origin-Agent-Cluster: \?1/);
  }
  assert.doesNotMatch(app, /\.style\.|cssText|setAttribute\(["']style/);
  assert.doesNotMatch(source, /style=\"/);
});

test("styles do not request third-party fonts that the CSP blocks", () => {
  for (const content of [css, source]) {
    assert.doesNotMatch(content, /fonts\.googleapis\.com/);
  }
});

test("styles honor reduced-motion preferences beyond entrance animations", () => {
  for (const content of [css, source]) {
    assert.match(content, /@media \(prefers-reduced-motion: reduce\)/);
    assert.match(content, /transition-duration: 0\.01ms !important/);
    assert.match(content, /animation-duration: 0\.01ms !important/);
  }
});
