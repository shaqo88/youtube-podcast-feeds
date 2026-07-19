import assert from "node:assert/strict";
import test from "node:test";

import { handleSubmit } from "../src/index.mjs";

const validRequest = () => new Request("https://worker.example/submit", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    source: "youtube",
    youtubeUrl: "https://www.youtube.com/@example",
    title: "Example lessons",
    slug: "example-lessons",
    speaker: "Example speaker",
    startDate: "2026-07-19",
    authorizationConfirmed: true,
  }),
});

function githubResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("private intake submission does not expose a GitHub issue URL", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url).includes("/git/trees/main")) return githubResponse({ tree: [] });
    if (String(url).includes("/issues?state=open")) return githubResponse([]);
    if (String(url).endsWith("/issues") && options.method === "POST") {
      return githubResponse({ number: 42, html_url: "https://github.com/shaqo88/torah-pod-intake/issues/42" }, 201);
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  try {
    const response = await handleSubmit(validRequest(), {
      GITHUB_TOKEN: "test-token",
      INTAKE_REPO: "shaqo88/torah-pod-intake",
      SOURCE_REPO: "shaqo88/youtube-podcast-feeds",
      ALLOWED_ORIGINS: "https://torah-pod.pages.dev",
    });
    assert.equal(response.status, 201);
    assert.deepEqual(await response.json(), { ok: true });
    assert.ok(calls.some((call) => call.url.endsWith("/repos/shaqo88/torah-pod-intake/issues")));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("submission requires a rights confirmation", async () => {
  const request = validRequest();
  const payload = await request.json();
  payload.authorizationConfirmed = false;
  const response = await handleSubmit(new Request("https://worker.example/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }), {});

  assert.equal(response.status, 400);
  const body = await response.json();
  assert.match(body.errors.join(" "), /confirm/i);
});
