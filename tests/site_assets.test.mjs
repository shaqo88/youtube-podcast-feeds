import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync("public/assets/app.js", "utf8");
const worker = readFileSync("public/sw.js", "utf8");
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
