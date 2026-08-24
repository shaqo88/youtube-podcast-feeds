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
