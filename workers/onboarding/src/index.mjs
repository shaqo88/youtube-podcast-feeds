const MAX_LENGTHS = {
  title: 200,
  slug: 80,
  speaker: 200,
  description: 4000,
  artwork: 500,
  contact: 320,
  notes: 2000,
  sourceUrl: 500,
  youtubeUrl: 500,
  driveUrl: 500,
};

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SOURCE_DEFINITIONS = {
  youtube: {
    labels: ["youtube-onboarding"],
    urlFields: ["youtube"],
  },
  youtube_playlist: {
    labels: ["youtube-onboarding"],
    urlFields: ["youtube"],
  },
  drive: {
    labels: ["drive-onboarding"],
    urlFields: ["drive"],
  },
  youtube_drive: {
    labels: ["youtube-onboarding", "drive-onboarding"],
    urlFields: ["youtube", "drive"],
  },
  youtube_playlist_drive: {
    labels: ["youtube-onboarding", "drive-onboarding"],
    urlFields: ["youtube", "drive"],
  },
};

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
  if (source === "youtube" || source === "youtube_playlist") {
    return host === "youtube.com" || host.endsWith(".youtube.com") || host === "youtu.be";
  }
  if (source === "any") {
    return true;
  }
  return host === "drive.google.com";
}

function sourceDefinition(source) {
  return SOURCE_DEFINITIONS[source] || null;
}

function sourceUrls(payload) {
  const definition = sourceDefinition(payload.source);
  return {
    youtube: payload.youtubeUrl || (definition?.urlFields.includes("drive") ? "" : payload.sourceUrl),
    drive: payload.driveUrl || (definition?.urlFields.includes("youtube") ? "" : payload.sourceUrl),
  };
}

function validateEmail(value) {
  if (!value) {
    return true;
  }
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function isYouTubePlaylistUrl(value) {
  try {
    return Boolean(new URL(value).searchParams.get("list"));
  } catch {
    return false;
  }
}

function normalizePayload(raw) {
  const source = trim(raw.source);
  const payload = {
    source,
    sourceUrl: truncate(raw.sourceUrl, MAX_LENGTHS.sourceUrl),
    youtubeUrl: truncate(raw.youtubeUrl, MAX_LENGTHS.youtubeUrl),
    driveUrl: truncate(raw.driveUrl, MAX_LENGTHS.driveUrl),
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
  const definition = sourceDefinition(payload.source);
  if (!definition) {
    errors.push("Invalid source type.");
  }
  if (!payload.speaker) {
    errors.push("Speaker / rabbi name is required.");
  }
  if (!payload.slug || !SLUG_RE.test(payload.slug)) {
    errors.push("Feed URL name is required and must use only lowercase English letters, numbers, and hyphens.");
  }
  const urls = sourceUrls(payload);
  if (definition?.urlFields.includes("youtube") && (!urls.youtube || !validateUrl(urls.youtube, "youtube"))) {
    errors.push("YouTube URL is invalid.");
  }
  if (definition?.urlFields.includes("drive") && (!urls.drive || !validateUrl(urls.drive, "drive"))) {
    errors.push("Google Drive folder URL is invalid.");
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
  return ["needs-approval", ...(sourceDefinition(source)?.labels || [])];
}

function sourceLabel(payload) {
  const urls = sourceUrls(payload);
  const definition = sourceDefinition(payload.source);
  const hasYouTube = definition?.urlFields.includes("youtube");
  const hasDrive = definition?.urlFields.includes("drive");
  const isPlaylist = hasYouTube && isYouTubePlaylistUrl(urls.youtube);
  if (hasYouTube && hasDrive) {
    return isPlaylist ? "YouTube playlist + Google Drive folder" : "YouTube channel + Google Drive folder";
  }
  if (hasYouTube) {
    return isPlaylist ? "YouTube playlist" : "YouTube channel";
  }
  return "Google Drive folder";
}

function issueTitle(payload) {
  const youtubeUrl = sourceUrls(payload).youtube;
  const isPlaylist = isYouTubePlaylistUrl(youtubeUrl);
  const definition = sourceDefinition(payload.source);
  let prefix = "Drive";
  if (definition?.urlFields.includes("youtube")) {
    prefix = isPlaylist ? "YouTube playlist" : "YouTube";
  }
  if (definition?.urlFields.includes("youtube") && definition?.urlFields.includes("drive")) {
    prefix = `${prefix} + Drive`;
  }
  return `${prefix} podcast onboarding: ${payload.podcastName}`;
}

function issueBody(payload) {
  const definition = sourceDefinition(payload.source);
  const { youtube: youtubeUrl, drive: driveUrl } = sourceUrls(payload);
  const isPlaylist = isYouTubePlaylistUrl(youtubeUrl);
  const hasYouTube = definition?.urlFields.includes("youtube");
  const hasDrive = definition?.urlFields.includes("drive");
  const creatorLines = [];
  if (hasYouTube) {
    creatorLines.push(
      isPlaylist
        ? "- YouTube playlist is public or accessible: yes"
        : "- YouTube channel is public or accessible: yes",
    );
  }
  if (hasDrive) {
    creatorLines.push(
      "- Drive folder shared with podcast-sync@torah-pod-podcast-sync.iam.gserviceaccount.com: yes",
      hasYouTube
        ? "- Finished Drive files will use `YYYY-MM-DD - Episode Title.ext`: yes"
        : "- Finished files will use `YYYY-MM-DD - Episode Title.ext`: yes",
    );
  }
  return [
    "## Podcast onboarding request",
    "",
    `- Source type: ${sourceLabel(payload)}`,
    ...(youtubeUrl ? [`- YouTube URL: ${youtubeUrl}`] : []),
    ...(driveUrl ? [`- Drive URL: ${driveUrl}`] : []),
    ...(!youtubeUrl && !driveUrl ? [`- Source URL: ${payload.sourceUrl}`] : []),
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
    hasYouTube && hasDrive
      ? `1. Review the YouTube source at ${youtubeUrl}, then run the Check Drive Folder workflow for ${driveUrl}.`
      : hasDrive
        ? `1. Run the Check Drive Folder workflow for ${driveUrl}.`
        : `1. Review the YouTube source at ${youtubeUrl}.`,
    "2. If approved, add the `approved` label.",
    "3. The approval workflow creates the show, syncs first episodes, deploys the feed, comments here, and closes this issue.",
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
