import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const source = readFileSync("podcast_feeds/web/app.js", "utf8");
const functions = ["normalizeSearchText", "prepareSearchText", "preparedSearchScore", "searchScore", "rankPreparedEpisodes"]
  .map((name) => source.match(new RegExp(`  function ${name}[\\s\\S]*?\\n  }`))[0]).join("\n");
const search = {};
runInNewContext(functions, search);

test("the committed app bundle matches its generated source", () => {
  const listening = readFileSync("podcast_feeds/web/listening-pages.js", "utf8");
  assert.equal(readFileSync("public/assets/app.js", "utf8"), source.replace("  // LISTENING_PAGES", listening));
});

test("prepared scores retain title, show, author, and multi-token relevance", () => {
  const text = search.prepareSearchText("פרשת נח", "שיעורי חסידות", "הרב משה");
  for (const [query, expected] of [["פרשת נח", 500], ["פרשת", 400], ["נח", 300], ["חסידות", 200], ["משה", 150], ["נח משה", 100], ["אין", 0]]) {
    assert.equal(search.preparedSearchScore(query, query.split(" "), text), expected, query);
    assert.equal(search.searchScore(query, "פרשת נח", "שיעורי חסידות", "הרב משה"), expected, query);
  }
});

test("prepared ranking keeps date ties stable and returns original unmodified records", () => {
  const items = [
    { id: "older", title: "נח", published: "20250101" },
    { id: "newer", title: "נח", published: "20260101" },
    { id: "same-date", title: "נח", published: "20260101" },
    { id: "prefix", title: "נח ומשפחתו", published: "20261028" },
    { id: "none", title: "אברהם", published: "20261028" },
  ].map(Object.freeze);
  const prepared = items.map(item => ({ item, text: search.prepareSearchText(item.title) }));
  const matches = search.rankPreparedEpisodes("נח", prepared);
  assert.deepEqual(Array.from(matches, item => item.id), ["newer", "same-date", "older", "prefix"]);
  assert.equal(matches[0], items[1]);
  assert.equal("score" in matches[0], false);
});

// Compatibility oracle: the pre-change algorithm. This intentionally stays
// independent of the prepared scorer so a future ranking change is visible.
function originalScore(query, title, show, author) {
  const normalizedTitle = search.normalizeSearchText(title);
  const normalizedShow = search.normalizeSearchText(show);
  const normalizedAuthor = search.normalizeSearchText(author);
  const tokens = query.split(" ").filter(Boolean);
  if (!tokens.every(token => `${normalizedTitle} ${normalizedShow} ${normalizedAuthor}`.includes(token))) return 0;
  if (normalizedTitle === query) return 500;
  if (normalizedTitle.startsWith(query)) return 400;
  if (tokens.every(token => normalizedTitle.includes(token))) return 300;
  if (normalizedShow.includes(query)) return 200;
  if (normalizedAuthor.includes(query)) return 150;
  return 100;
}

test("real-index rankings match the original algorithm for Hebrew input variants", () => {
  const episodes = JSON.parse(readFileSync("public/search-index.json", "utf8")).episodes;
  const catalog = JSON.parse(readFileSync("public/catalog.json", "utf8"));
  const shows = new Map(catalog.map(show => [show.slug, show]));
  const prepared = episodes.map(item => {
    const show = shows.get(item.show_slug);
    return { item, text: search.prepareSearchText(item.title, show?.title, show?.author) };
  });
  for (const input of ["נח", "נחמ", "נחמן", "נחמנסון", "פרשת נח", "תורה", "שַׁבָּת", "שבת", "תשפ״ז", 'תשפ"ז', "תשפז", "תורה־פוד", "תורה פוד", "ביטחון", "בטחון", "ווכטר", "וועכטר", "איןתוצאותxyz"]) {
    const query = search.normalizeSearchText(input);
    const original = episodes.map(item => {
      const show = shows.get(item.show_slug);
      return { ...item, score: originalScore(query, item.title, show?.title, show?.author) };
    }).filter(item => item.score > 0).sort((a, b) => b.score - a.score || String(b.published).localeCompare(String(a.published)));
    assert.deepEqual(Array.from(search.rankPreparedEpisodes(query, prepared), item => item.id), original.map(item => item.id), input);
  }
});

function fixture() {
  const handlers = {};
  const input = { value: "", addEventListener: (name, fn) => { handlers[name] = fn; } };
  const status = { textContent: "" }, list = { markup: "" }, heading = { dataset: {} }, more = { addEventListener() {} };
  const card = { dataset: { showSlug: "show", showTitle: "חסידות", showAuthor: "משה" } };
  const page = { dataset: {}, isConnected: true, querySelector: selector => ({
    "[data-catalog-search]": input, "[data-search-status]": status,
    "[data-search-podcast-catalog]": { querySelectorAll: () => [card], appendChild() {} },
    "[data-search-episode-results]": list, "[data-search-episode-heading]": heading,
    "[data-search-more]": more,
  })[selector] };
  let resolveIndex, rejectIndex, loads = 0, normalizations = 0;
  const pending = new Promise((resolve, reject) => { resolveIndex = resolve; rejectIndex = reject; });
  const context = {
    document: { querySelector: () => page, addEventListener() {} },
    listBindingsAbortController: null,
    loadLatestMetadata: async () => ({ shows: [{ latest: [{ id: "recent" }] }] }),
    loadSearchIndex: () => { loads++; return pending; },
    window: { TorahPodListening: { recentEpisodes: items => items } },
    t: key => key, replaceEpisodeList: (_, markup) => { list.markup = markup; },
    searchEpisodeMarkup: item => item.id,
    setupEpisodes() {}, updateVisibleEpisodeActions() {}, updateVisibleEpisodeProgress() {},
  };
  runInNewContext(functions + "\n" + source.match(/  function setupCatalogSearch[\s\S]*?\n  }/)[0], context);
  const normalize = context.normalizeSearchText;
  context.normalizeSearchText = value => { normalizations++; return normalize(value); };
  context.setupCatalogSearch();
  return { context, page, input, status, list, more, resolveIndex, rejectIndex,
    normalizations: () => normalizations, loads: () => loads,
    type: query => { input.value = query; return handlers.input(); } };
}

const episodes = [{ id: "match", title: "פרשת נח", show_slug: "show", published: "20261028" }];

test("warm inputs reuse prepared catalog text while retaining immediate input handling", async () => {
  const f = fixture();
  await Promise.resolve();
  const pending = f.type("פרשת");
  assert.equal(f.status.textContent, "search_loading");
  f.resolveIndex(episodes); await pending;
  assert.equal(f.list.markup, "match");
  const before = f.normalizations();
  await f.type("נח");
  // One query and the three small podcast-card fields; no episode normalization.
  assert.equal(f.normalizations() - before, 4);
  assert.equal(f.list.markup, "match");
});

test("rapid edits use only the last query when the shared index resolves", async () => {
  const f = fixture();
  const first = f.type("פרשת"), last = f.type("אין");
  f.resolveIndex(episodes); await Promise.all([first, last]);
  assert.equal(f.list.markup, "");
  assert.equal(f.status.textContent, "no_search_results");
});

test("clearing and leaving ignore a pending search response", async () => {
  const f = fixture();
  const pending = f.type("פרשת"); await f.type("");
  f.resolveIndex(episodes); await pending;
  assert.equal(f.list.markup, "recent");
  assert.equal(f.status.textContent, "");
  const g = fixture(); await new Promise(setImmediate);
  const leaving = g.type("פרשת"); g.page.isConnected = false;
  g.resolveIndex(episodes); await leaving;
  assert.equal(g.list.markup, "recent");
});

test("index load failures remain visible and do not prepare broken data", async () => {
  const f = fixture();
  const pending = f.type("פרשת"); f.rejectIndex(new Error("503")); await pending;
  assert.equal(f.status.textContent, "search_failed");
});

test("the index loader shares pending requests and retries after failures", async () => {
  let calls = 0, resolve;
  const pending = new Promise(r => { resolve = r; });
  const context = { searchIndexPromise: null, basePath: "https://example.test/", location: { href: "https://example.test/search/" }, URL,
    fetch: () => { calls++; return pending; } };
  runInNewContext(source.match(/  function loadSearchIndex[\s\S]*?\n  }/)[0], context);
  const first = context.loadSearchIndex();
  assert.equal(context.loadSearchIndex(), first);
  assert.equal(calls, 1);
  resolve({ ok: false, status: 503 });
  await assert.rejects(first, /503/);
  context.fetch = async () => { calls++; return { ok: true, json: async () => ({ schema_version: 1, episodes }) }; };
  assert.equal(await context.loadSearchIndex(), episodes);
  assert.equal(calls, 2);
  assert.equal(await context.loadSearchIndex(), episodes);
  assert.equal(calls, 2);
});
