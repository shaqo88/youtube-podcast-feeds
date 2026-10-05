import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const { escapeMarkup, recentEpisodes, pageEpisodes, retryDecoderOnce } = require("../podcast_feeds/web/listen-core.js");
const episode = (id, show, published) => ({ id, show_slug: show, published });

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
