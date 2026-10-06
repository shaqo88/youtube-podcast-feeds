import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
const require = createRequire(import.meta.url);
const { storedVolume, escapeMarkup, recentEpisodes, pageEpisodes, retryDecoderOnce } = require("../podcast_feeds/web/listen-core.js");
const episode = (id, show, published) => ({ id, show_slug: show, published });

// Exercise the generated client functions with small DOM/media doubles. This
// verifies runtime behavior without starting real audio in the test runner.
function clientFunctions(names, context) {
  const bundle = readFileSync("public/assets/app.js", "utf8");
  const functions = names.map((name) => {
    const match = bundle.match(new RegExp(`  function ${name}\\([^]*?\\n  }`));
    assert.ok(match, `generated function ${name}`);
    return match[0];
  });
  runInNewContext(`${functions.join("\n")}\nthis.client = {${names.join(",")}};`, context);
  return context.client;
}

test("volume is applied before a new episode plays, including intentional mute", () => {
  let preference = null;
  const context = { window: { TorahPodListening: { storedVolume } },
    safeGet: () => preference, updateVolumeControl: () => {}, applyPlaybackRate: () => {} };
  const client = clientFunctions(["playbackVolume", "applyPlaybackVolume", "loadAudio"], context);
  const audio = { src: "", dataset: { audioSrc: "https://example.org/episode.mp3" }, volume: 0, muted: true };
  client.loadAudio(audio);
  assert.equal(audio.volume, 1);
  assert.equal(audio.muted, false);
  preference = 0;
  client.loadAudio(audio);
  assert.equal(audio.volume, 0);
  assert.equal(audio.muted, true);
  preference = 0.4;
  client.loadAudio(audio);
  assert.equal(audio.volume, 0.4);
  assert.equal(audio.muted, false);
});

test("seek control follows media time and becomes usable when duration is known", () => {
  const seek = { setAttribute(name, value) { this[name] = value; } };
  const audio = { duration: NaN, currentTime: 0 };
  let displayed;
  const context = { player: {}, activeAudio: audio, activeEpisode: null, activeState: null,
    playerSeek: seek, seeking: false, updatePlayerTime: (...args) => { displayed = args; },
    updateMiniProgress: () => {}, formatTime: (value) => String(value) };
  const client = clientFunctions(["updatePlayerProgress"], context);
  client.updatePlayerProgress();
  assert.equal(seek.disabled, true);
  audio.duration = 1800;
  audio.currentTime = 127;
  client.updatePlayerProgress();
  assert.equal(seek.disabled, false);
  assert.equal(seek.max, "1800");
  assert.equal(seek.value, "127");
  assert.deepEqual(displayed, [127, 1800]);
});

test("search opens with recent episodes and loads the full index only for a query", async () => {
  const input = { value: "", addEventListener(_, handler) { this.onInput = handler; } };
  const list = { innerHTML: "server-rendered episodes" };
  const status = {};
  const heading = { dataset: {} };
  const page = { dataset: {}, isConnected: true, querySelector: (selector) => ({
    "[data-catalog-search]": input, "[data-search-episode-results]": list,
    "[data-search-status]": status, "[data-search-episode-heading]": heading,
  })[selector] || null };
  let fullIndexLoads = 0;
  const context = { document: { querySelector: () => page, addEventListener: () => {} },
    window: { TorahPodListening: { recentEpisodes } }, listBindingsAbortController: null,
    normalizeSearchText: (value) => value.trim(), t: (key) => key,
    loadLatestMetadata: async () => ({ shows: [{ latest: [episode("recent", "a", "20261005")] }] }),
    loadSearchIndex: async () => { fullIndexLoads++; return [{ ...episode("match", "a", "20261005"), title: "Torah" }]; },
    searchScore: (query, title) => title?.toLowerCase().includes(query.toLowerCase()) ? 1 : 0,
    searchEpisodeMarkup: (item) => item.id,
    replaceEpisodeList: (element, markup) => { element.innerHTML = markup; },
    setupEpisodes: () => {}, updateVisibleEpisodeActions: () => {}, updateVisibleEpisodeProgress: () => {} };
  const client = clientFunctions(["setupCatalogSearch"], context);
  client.setupCatalogSearch();
  await new Promise(setImmediate);
  assert.equal(list.innerHTML, "recent");
  assert.equal(fullIndexLoads, 0);
  input.value = "Torah";
  await input.onInput();
  assert.equal(list.innerHTML, "match");
  assert.equal(fullIndexLoads, 1);
  input.value = "";
  await input.onInput();
  assert.equal(list.innerHTML, "recent");
  assert.equal(fullIndexLoads, 1);
  context.loadLatestMetadata = async () => { throw new Error("offline"); };
  await input.onInput();
  assert.equal(list.innerHTML, "recent");
  assert.equal(status.textContent, "episodes_failed");
});

test("fresh listeners start audibly and an explicit mute remains distinguishable from no preference", () => {
  for (const missing of [null, undefined, "", "invalid", false]) assert.equal(storedVolume(missing), 1);
  assert.equal(storedVolume(0), 0);
  assert.equal(storedVolume("0"), 0);
  assert.equal(storedVolume(0.45), 0.45);
  assert.equal(storedVolume(2), 1);
});

test("catalog text cannot break quoted attributes or inject markup", () => {
  assert.equal(escapeMarkup('הרה"ג & <episode>'), 'הרה&quot;ג &amp; &lt;episode&gt;');
  assert.equal(escapeMarkup('\" onerror=\'alert(1)\''), '&quot; onerror=&#39;alert(1)&#39;');
  assert.equal(escapeMarkup('&quot;'), '&amp;quot;');
});

test("decoder recovery retries once and never restarts a stopped or replaced episode", () => {
  let retries = 0;
  const audio = { error: { code: 3 }, dataset: {} };
  assert.equal(retryDecoderOnce(audio, false, () => retries++), false);
  assert.equal(retryDecoderOnce(audio, true, () => retries++), true);
  assert.equal(retryDecoderOnce(audio, true, () => retries++), false);
  assert.equal(retries, 1);
  assert.equal(retryDecoderOnce({ error: { code: 2 }, dataset: {} }, true, () => retries++), false);
  assert.equal(retryDecoderOnce({ error: null, dataset: {} }, true, () => retries++), false);
});

test("a busy unfollowed show cannot crowd out followed episodes", () => {
  const busy = Array.from({ length: 100 }, (_, i) => episode(`busy:${i}`, "busy", "20261005"));
  const older = episode("quiet:one", "quiet", "20260101");
  assert.deepEqual(recentEpisodes([...busy, older], ["quiet"]), [older]);
});
test("followed episodes are merged before the display limit with no age cutoff", () => {
  const items = [episode("a:1", "a", "20261001"), episode("b:1", "b", "20250101"), episode("b:2", "b", "20240901")];
  assert.deepEqual(recentEpisodes(items, ["a", "b"], 2).map((item) => item.id), ["a:1", "b:1"]);
});
test("duplicate identities render once and distinct shows retain their identities", () => {
  const a = episode("a:1", "a", "20261001"), b = episode("b:1", "b", "20261001");
  assert.equal(recentEpisodes([a, a, b]).length, 2);
});
test("pagination reaches the final item without overlap", () => {
  const items = Array.from({ length: 41 }, (_, i) => episode(`a:${i}`, "a", "20261001"));
  const pages = [0, 1, 2].map((page) => pageEpisodes(items, page));
  assert.deepEqual(pages.map((page) => page.episodes.length), [20, 20, 1]);
  assert.equal(new Set(pages.flatMap((page) => page.episodes.map((item) => item.id))).size, 41);
  assert.equal(pages[2].hasMore, false);
});
test("published episode pages have unique identities and complete pagination", () => {
  const index = JSON.parse(readFileSync("public/metadata/v1/latest.json", "utf8"));
  for (const show of index.shows) {
    const items = [];
    for (let page = 1; page <= show.pages; page++) {
      const data = JSON.parse(readFileSync(`public/metadata/v1/shows/${show.slug}/${page}.json`, "utf8"));
      assert.ok(data.episodes.length <= 20);
      assert.equal(data.next_page, page < show.pages ? page + 1 : null);
      items.push(...data.episodes);
    }
    assert.equal(items.length, show.total);
    assert.equal(new Set(items.map((item) => item.id)).size, show.total);
  }
});
