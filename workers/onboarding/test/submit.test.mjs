import assert from "node:assert/strict";
import test from "node:test";

import worker, { handleSubmit } from "../src/index.mjs";

const origin = "https://torah-pod.pages.dev";
const validPayload = {
  source: "youtube",
  youtubeUrl: "https://www.youtube.com/@example",
  title: "Example lessons",
  slug: "example-lessons",
  speaker: "Example speaker",
  startDate: "2026-07-19",
  authorizationConfirmed: true,
  turnstileToken: "test-turnstile-token",
};

function request(payload = validPayload, options = {}) {
  return new Request("https://worker.example/submit", {
    method: options.method || "POST",
    headers: {
      Origin: options.origin === undefined ? origin : options.origin,
      "Content-Type": options.contentType || "application/json",
      ...(options.headers || {}),
    },
    body: options.body === undefined ? JSON.stringify(payload) : options.body,
  });
}

function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

function env(overrides = {}) {
  return {
    GITHUB_TOKEN: "test-token",
    INTAKE_REPO: "shaqo88/torah-pod-intake",
    SOURCE_REPO: "shaqo88/youtube-podcast-feeds",
    ALLOWED_ORIGINS: origin,
    TURNSTILE_SECRET: "test-secret",
    TURNSTILE_ALLOWED_HOSTNAMES: "torah-pod.pages.dev,shaqo88.github.io",
    BUILD_SHA: "a".repeat(40),
    BUILD_TIME: "2026-07-22T10:00:00Z",
    BUILD_RUN_ID: "123",
    BUILD_RUN_URL: "https://github.example/run/123",
    PER_IP_SUBMIT_LIMITER: { limit: async () => ({ success: true }) },
    GLOBAL_SUBMIT_LIMITER: { limit: async () => ({ success: true }) },
    ...overrides,
  };
}

async function withFetch(handler, callback) {
  const original = globalThis.fetch;
  globalThis.fetch = handler;
  try {
    await callback();
  } finally {
    globalThis.fetch = original;
  }
}

function successfulFetch(calls) {
  return async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url).includes("/turnstile/v0/siteverify")) {
      return json({ success: true, action: "onboarding", hostname: "torah-pod.pages.dev" });
    }
    if (String(url).includes("/git/trees/main")) return json({ tree: [] });
    if (String(url).includes("/issues?state=open")) return json([]);
    if (String(url).endsWith("/issues") && options.method === "POST") return json({ number: 42 }, 201);
    throw new Error(`Unexpected fetch: ${url}`);
  };
}

test("private intake success is origin-scoped and does not expose a GitHub URL", async () => {
  const calls = [];
  await withFetch(successfulFetch(calls), async () => {
    const response = await handleSubmit(request(), env());
    assert.equal(response.status, 201);
    assert.deepEqual(await response.json(), { ok: true });
    assert.equal(response.headers.get("Access-Control-Allow-Origin"), origin);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    assert.equal(response.headers.get("X-Content-Type-Options"), "nosniff");
    assert.ok(calls.some((call) => call.url.includes("siteverify")));
    assert.ok(calls.some((call) => call.url.endsWith("/repos/shaqo88/torah-pod-intake/issues")));
  });
});

test("origin, content type, malformed JSON, and oversized bodies are rejected before network calls", async () => {
  for (const candidate of [
    request(validPayload, { origin: "https://evil.example" }),
    request(validPayload, { contentType: "text/plain" }),
    request(validPayload, { body: "{" }),
    request(validPayload, { body: JSON.stringify({ ...validPayload, notes: "x".repeat(17_000) }) }),
  ]) {
    let calls = 0;
    await withFetch(async () => { calls += 1; throw new Error("must not fetch"); }, async () => {
      const response = await handleSubmit(candidate, env());
      assert.ok([400, 403, 413, 415].includes(response.status));
      assert.equal(calls, 0);
    });
  }
});

test("rights, rate limit, and Turnstile failures stop before GitHub/feed work", async () => {
  const noRights = request({ ...validPayload, authorizationConfirmed: false });
  await withFetch(async () => { throw new Error("must not fetch"); }, async () => {
    assert.equal((await handleSubmit(noRights, env())).status, 400);
  });

  let calls = [];
  await withFetch(successfulFetch(calls), async () => {
    const response = await handleSubmit(request(), env({ PER_IP_SUBMIT_LIMITER: { limit: async () => ({ success: false }) } }));
    assert.equal(response.status, 429);
    assert.equal(response.headers.get("Retry-After"), "60");
    assert.equal(calls.length, 0);
  });

  calls = [];
  await withFetch(async (url, options = {}) => {
    calls.push({ url: String(url), options });
    if (String(url).includes("siteverify")) return json({ success: false });
    throw new Error("GitHub/feed must not be called");
  }, async () => {
    const response = await handleSubmit(request(), env());
    assert.equal(response.status, 403);
    assert.equal(calls.length, 1);
  });
});

test("unsafe feed URLs are rejected and unsafe redirects never become metadata fetch targets", async () => {
  const unsafe = request({ ...validPayload, source: "feed", feedUrl: "https://127.0.0.1/feed.xml", youtubeUrl: "", speaker: "", slug: "", startDate: "" });
  await withFetch(async () => { throw new Error("must not fetch"); }, async () => {
    assert.equal((await handleSubmit(unsafe, env())).status, 400);
  });

  const calls = [];
  await withFetch(async (url, options = {}) => {
    calls.push(String(url));
    if (String(url).includes("siteverify")) return json({ success: true, action: "onboarding", hostname: "torah-pod.pages.dev" });
    if (String(url) === "https://example.com/feed.xml") return new Response(null, { status: 302, headers: { Location: "http://127.0.0.1/feed.xml" } });
    if (String(url).includes("/git/trees/main")) return json({ tree: [] });
    if (String(url).includes("/issues?state=open")) return json([]);
    if (String(url).endsWith("/issues") && options.method === "POST") return json({ number: 42 }, 201);
    throw new Error(`Unexpected fetch: ${url}`);
  }, async () => {
    const response = await handleSubmit(request({ ...validPayload, source: "feed", feedUrl: "https://example.com/feed.xml", youtubeUrl: "", speaker: "", slug: "", startDate: "" }), env());
    assert.equal(response.status, 201);
    assert.equal(calls.filter((url) => url.includes("127.0.0.1")).length, 0);
  });
});

test("preflight accepts only the configured browser origin", async () => {
  const response = await worker.fetch(new Request("https://worker.example/submit", { method: "OPTIONS", headers: { Origin: origin } }), env());
  assert.equal(response.status, 204);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), origin);
  const rejected = await worker.fetch(new Request("https://worker.example/submit", { method: "OPTIONS", headers: { Origin: "https://evil.example" } }), env());
  assert.equal(rejected.status, 403);
});

test("health exposes bounded deployment provenance without secrets", async () => {
  const response = await worker.fetch(new Request("https://worker.example/health"), env());
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(body.ok, true);
  assert.deepEqual(body.deployment, {
    schema_version: 1,
    target: "onboarding-worker",
    revision: "a".repeat(40),
    deployed_at: "2026-07-22T10:00:00Z",
    run_id: 123,
    run_url: "https://github.example/run/123",
  });
  assert.equal(JSON.stringify(body).includes("test-secret"), false);
});
