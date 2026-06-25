const MAX_LENGTHS = {
  title: 200,
  slug: 80,
  speaker: 200,
  description: 4000,
  artwork: 500,
  contact: 320,
  notes: 2000,
  sourceUrl: 500,
};

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function trim(value) {
  return typeof value === "string" ? value.trim() : "";
}

function truncate(value, maxLength) {
  value = trim(value);
  return value.length > maxLength ? value.slice(0, maxLength) : value;
}

function jsonResponse(request, env, status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(request, env),
    },
  });
}

function corsHeaders(request, env) {
  const origin = request.headers.get("Origin") || "";
  const allowedOrigins = String(env.ALLOWED_ORIGINS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  const allowOrigin = allowedOrigins.includes(origin) ? origin : allowedOrigins[0] || "*";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

function validateUrl(value, source) {
  let url;
  try {
    url = new URL(value);
  } catch {
    return false;
  }

  if (url.protocol !== "https:") {
    return false;
  }

  const host = url.hostname.toLowerCase();
  if (source === "youtube") {
    return host === "youtube.com" || host.endsWith(".youtube.com") || host === "youtu.be";
  }
  if (source === "any") {
    return true;
  }
  return host === "drive.google.com";
}

function validateEmail(value) {
  if (!value) {
    return true;
  }
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function normalizePayload(raw) {
  const source = trim(raw.source);
  const payload = {
    source,
    sourceUrl: truncate(raw.sourceUrl, MAX_LENGTHS.sourceUrl),
    title: truncate(raw.title, MAX_LENGTHS.title),
    slug: truncate(raw.slug, MAX_LENGTHS.slug).toLowerCase(),
    speaker: truncate(raw.speaker, MAX_LENGTHS.speaker),
    startDate: trim(raw.startDate),
    description: truncate(raw.description, MAX_LENGTHS.description),
    artwork: truncate(raw.artwork, MAX_LENGTHS.artwork),
    contact: truncate(raw.contact, MAX_LENGTHS.contact),
    notes: truncate(raw.notes, MAX_LENGTHS.notes),
    honeypot: trim(raw.companyWebsite),
  };
  payload.podcastName = payload.title || payload.speaker;
  return payload;
}

function validatePayload(payload) {
  const errors = [];
  if (!["youtube", "drive"].includes(payload.source)) {
    errors.push("Invalid source type.");
  }
  if (!payload.speaker) {
    errors.push("Speaker / rabbi name is required.");
  }
  if (payload.slug && !SLUG_RE.test(payload.slug)) {
    errors.push("Feed URL name must use only lowercase English letters, numbers, and hyphens.");
  }
  if (!payload.sourceUrl || !validateUrl(payload.sourceUrl, payload.source)) {
    errors.push("Source URL is invalid.");
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.startDate)) {
    errors.push("Start date must be YYYY-MM-DD.");
  }
  if (!validateEmail(payload.contact)) {
    errors.push("Contact email is invalid.");
  }
  if (payload.artwork && !validateUrl(payload.artwork, "any")) {
    errors.push("Artwork URL must be an https URL.");
  }
  return errors;
}

function issueLabels(source) {
  return source === "drive"
    ? ["drive-onboarding", "needs-approval"]
    : ["youtube-onboarding", "needs-approval"];
}

function issueTitle(payload) {
  const prefix = payload.source === "drive" ? "Drive" : "YouTube";
  return `${prefix} podcast onboarding: ${payload.podcastName}`;
}

function issueBody(payload) {
  const sourceLabel = payload.source === "drive" ? "Google Drive folder" : "YouTube channel";
  const checkLine = payload.source === "drive"
    ? `- [ ] Check Drive Folder workflow passed for ${payload.sourceUrl}.`
    : `- [ ] YouTube channel reviewed and channel ID found for ${payload.sourceUrl}.`;
  const creatorLines = payload.source === "drive"
    ? [
        "- Drive folder shared with podcast-sync@torah-pod-podcast-sync.iam.gserviceaccount.com: yes",
        "- Finished files will use `YYYY-MM-DD - Episode Title.ext`: yes",
      ]
    : ["- YouTube channel is public or accessible: yes"];

  return [
    "## Podcast onboarding request",
    "",
    `- Source type: ${sourceLabel}`,
    `- Source URL: ${payload.sourceUrl}`,
    `- Podcast name: ${payload.podcastName}`,
    `- Feed slug: ${payload.slug || "Not provided"}`,
    `- Speaker / rabbi: ${payload.speaker}`,
    `- Start date: ${payload.startDate}`,
    `- Artwork URL: ${payload.artwork || "Not provided"}`,
    `- Contact email: ${payload.contact || "Not provided"}`,
    "",
    "## Description",
    "",
    payload.description || "Use source description if available.",
    "",
    "## Additional notes",
    "",
    payload.notes || "None.",
    "",
    "## Creator confirmations",
    "",
    ...creatorLines,
    "- Torah Pod approval is required before a feed is created: yes",
    "",
    "## Maintainer approval",
    "",
    checkLine,
    "- [ ] Torah Pod approved this podcast.",
    "- [ ] Show config added.",
    "- [ ] First sync completed.",
  ].join("\n");
}

async function createGitHubIssue(env, payload, includeLabels = true) {
  const repo = env.GITHUB_REPO || "shaqo88/youtube-podcast-feeds";
  const body = {
    title: issueTitle(payload),
    body: issueBody(payload),
  };
  if (includeLabels) {
    body.labels = issueLabels(payload.source);
  }

  const response = await fetch(`https://api.github.com/repos/${repo}/issues`, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "torah-pod-onboarding-worker",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify(body),
  });

  const responseBody = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(responseBody.message || "GitHub issue creation failed.");
    error.status = response.status;
    error.responseBody = responseBody;
    throw error;
  }
  return responseBody;
}

async function handleSubmit(request, env) {
  let raw;
  try {
    raw = await request.json();
  } catch {
    return jsonResponse(request, env, 400, { ok: false, error: "Invalid JSON." });
  }

  const payload = normalizePayload(raw);
  if (payload.honeypot) {
    return jsonResponse(request, env, 200, { ok: true, ignored: true });
  }

  const errors = validatePayload(payload);
  if (errors.length > 0) {
    return jsonResponse(request, env, 400, { ok: false, errors });
  }

  if (!env.GITHUB_TOKEN) {
    return jsonResponse(request, env, 500, { ok: false, error: "Worker is missing GITHUB_TOKEN." });
  }

  let issue;
  try {
    issue = await createGitHubIssue(env, payload, true);
  } catch (error) {
    if (error.status !== 422) {
      console.error("GitHub issue creation failed", error.responseBody || error);
      return jsonResponse(request, env, 502, { ok: false, error: "Could not create GitHub issue." });
    }
    issue = await createGitHubIssue(env, payload, false);
  }

  return jsonResponse(request, env, 201, {
    ok: true,
    issueUrl: issue.html_url,
    issueNumber: issue.number,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request, env) });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse(request, env, 200, { ok: true });
    }

    if (request.method === "POST" && url.pathname === "/submit") {
      return handleSubmit(request, env);
    }

    return jsonResponse(request, env, 404, { ok: false, error: "Not found." });
  },
};
