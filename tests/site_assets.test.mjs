import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync("public/assets/app.js", "utf8");
const worker = readFileSync("public/sw.js", "utf8");
const headers = readFileSync("public/_headers", "utf8");
const source = readFileSync("podcast_feeds/site.py", "utf8");

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

test("future generated pages avoid nested interactive player controls", () => {
  assert.match(source, /class=\"skip-link\" href=\"#main-content\"/);
  assert.match(source, /<main id=\"main-content\" tabindex=\"-1\">/);
  assert.match(source, /class=\"player-details\" type=\"button\" data-player-details/);
  assert.doesNotMatch(source, /class=\"player-main\" role=\"button\"/);
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
