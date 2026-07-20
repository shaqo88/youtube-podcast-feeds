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
  feedUrl: 500,
};

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const FOLDER_ID_RE = /\/folders\/([^/?#]+)/;
const PLAYLIST_ID_RE = /[?&]list=([^&#]+)/;
const FEED_METADATA_MAX_LENGTH = 200;
const MAX_REQUEST_BYTES = 16 * 1024;
const MAX_FEED_BYTES = 1024 * 1024;
const MAX_FEED_REDIRECTS = 3;
const SUBMIT_ACTION = "onboarding";
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
  feed: {
    labels: ["feed-onboarding"],
    urlFields: ["feed"],
  },
};

function trim(value) {
  return typeof value === "string" ? value.trim() : "";
}

function truncate(value, maxLength) {
  value = trim(value);
  return value.length > maxLength ? value.slice(0, maxLength) : value;
}

function allowedOrigins(env) {
  return String(env.ALLOWED_ORIGINS || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function requestOrigin(request, env) {
  const origin = request.headers.get("Origin") || "";
  return allowedOrigins(env).includes(origin) ? origin : "";
}

function jsonResponse(request, env, status, body, origin = requestOrigin(request, env)) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...(origin ? corsHeaders(origin) : {}),
    },
  });
}

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

function isUnsafeHost(host) {
  const value = String(host || "").toLowerCase().replace(/\.$/, "");
  if (!value || value === "localhost" || value.endsWith(".localhost") || value.endsWith(".local") || value.endsWith(".internal")) {
    return true;
  }
  if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(value) || value.includes(":")) return true;
  const parts = value.split(".").map(Number);
  if (parts.length === 4 && parts.every(Number.isInteger)) {
    const [a, b] = parts;
    return a === 0 || a === 10 || a === 127 || a >= 224 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
  }
  return false;
}

function safeHttpsUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443") || isUnsafeHost(url.hostname)) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

function validateUrl(value, source) {
  const url = safeHttpsUrl(value);
  if (!url) return false;

  const host = url.hostname.toLowerCase();
  if (source === "youtube" || source === "youtube_playlist") {
    return host === "youtube.com" || host.endsWith(".youtube.com") || host === "youtu.be";
  }
  if (source === "any" || source === "feed") {
    return true;
  }
  return host === "drive.google.com";
}

function sourceDefinition(source) {
  return SOURCE_DEFINITIONS[source] || null;
}

function sourceUrls(payload) {
  const definition = sourceDefinition(payload.source);
  const onlyField = definition?.urlFields.length === 1 ? definition.urlFields[0] : "";
  return {
    youtube: payload.youtubeUrl || (onlyField === "youtube" ? payload.sourceUrl : ""),
    drive: payload.driveUrl || (onlyField === "drive" ? payload.sourceUrl : ""),
    feed: payload.feedUrl || (onlyField === "feed" ? payload.sourceUrl : ""),
  };
}

function normalizeUrl(value) {
  value = trim(value);
  if (!value) {
    return "";
  }
  try {
    const url = new URL(value);
    url.protocol = url.protocol.toLowerCase();
    url.hostname = url.hostname.toLowerCase();
    url.hash = "";
    url.pathname = url.pathname.replace(/\/+$/, "");
    return url.toString().replace(/\/+$/, "");
  } catch {
    return value.replace(/\/+$/, "");
  }
}

function folderIdFromInput(value) {
  const match = FOLDER_ID_RE.exec(trim(value));
  return match?.[1] || trim(value);
}

function playlistIdFromInput(value) {
  const match = PLAYLIST_ID_RE.exec(trim(value));
  return match?.[1] || trim(value);
}

function signatureKey(type, value) {
  value = trim(value);
  return value ? `${type}\u0000${value}` : "";
}

function sourceSignatureKeysFromValues(type, values) {
  if (type === "youtube") {
    return [
      signatureKey("youtube", values.channel_id),
      signatureKey("youtube", normalizeUrl(values.channel_url)),
    ].filter(Boolean);
  }
  if (type === "youtube_playlist") {
    return [signatureKey("youtube_playlist", values.playlist_id)].filter(Boolean);
  }
  if (type === "drive") {
    return [signatureKey("drive", values.folder_id)].filter(Boolean);
  }
  if (type === "existing_feed") {
    return [signatureKey("existing_feed", normalizeUrl(values.feed_url))].filter(Boolean);
  }
  return [];
}

function requestedSourceSignatureKeys(payload) {
  const urls = sourceUrls(payload);
  if (payload.source === "drive") {
    return [signatureKey("drive", folderIdFromInput(urls.drive))].filter(Boolean);
  }
  if (payload.source === "feed") {
    return [signatureKey("existing_feed", normalizeUrl(urls.feed))].filter(Boolean);
  }
  if (payload.source === "youtube" || payload.source === "youtube_playlist") {
    if (isYouTubePlaylistUrl(urls.youtube)) {
      return [signatureKey("youtube_playlist", playlistIdFromInput(urls.youtube))].filter(Boolean);
    }
    return [signatureKey("youtube", normalizeUrl(urls.youtube))].filter(Boolean);
  }
  return [];
}

function unquoteYamlScalar(value) {
  value = trim(value);
  if (
    (value.startsWith("'") && value.endsWith("'")) ||
    (value.startsWith('"') && value.endsWith('"'))
  ) {
    return value.slice(1, -1).replace(/''/g, "'");
  }
  return value;
}

function assignYamlKeyValue(target, value) {
  value = trim(value);
  const match = value.match(/^([A-Za-z0-9_]+):\s*(.*?)\s*$/);
  if (match) {
    target[match[1]] = unquoteYamlScalar(match[2]);
  }
}

function sourceBlocksFromConfigYaml(configText) {
  const blocks = [];
  let inSources = false;
  let current = null;
  for (const rawLine of configText.split(/\r?\n/)) {
    const line = rawLine.replace(/\s+$/, "");
    if (/^sources:\s*$/.test(line)) {
      inSources = true;
      continue;
    }
    if (!inSources) {
      continue;
    }
    if (/^[A-Za-z0-9_]+:\s*/.test(line)) {
      break;
    }
    const item = line.match(/^\s*-\s*(.*)$/);
    if (item) {
      if (current) {
        blocks.push(current);
      }
      current = {};
      assignYamlKeyValue(current, item[1]);
      continue;
    }
    if (current) {
      assignYamlKeyValue(current, line);
    }
  }
  if (current) {
    blocks.push(current);
  }
  return blocks;
}

function fieldsFromIssueBody(body) {
  const fields = {};
  for (const line of String(body || "").split(/\r?\n/)) {
    const match = line.match(/^- ([^:]+):\s*(.*)$/);
    if (match) {
      fields[match[1].trim().toLowerCase()] = match[2].trim();
    }
  }
  return fields;
}

function issueSourceSignatureKeys(issue) {
  const fields = fieldsFromIssueBody(issue.body || "");
  const sourceType = fields["source type"] || "";
  if (fields["existing feed url"]) {
    return [signatureKey("existing_feed", normalizeUrl(fields["existing feed url"]))].filter(Boolean);
  }
  if (fields["drive url"]) {
    return [signatureKey("drive", folderIdFromInput(fields["drive url"]))].filter(Boolean);
  }
  if (fields["youtube url"]) {
    if (/playlist/i.test(sourceType) || isYouTubePlaylistUrl(fields["youtube url"])) {
      return [signatureKey("youtube_playlist", playlistIdFromInput(fields["youtube url"]))].filter(Boolean);
    }
    return [signatureKey("youtube", normalizeUrl(fields["youtube url"]))].filter(Boolean);
  }
  return [];
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
    feedUrl: truncate(raw.feedUrl, MAX_LENGTHS.feedUrl),
    title: truncate(raw.title, MAX_LENGTHS.title),
    slug: truncate(raw.slug, MAX_LENGTHS.slug).toLowerCase(),
    speaker: truncate(raw.speaker, MAX_LENGTHS.speaker),
    startDate: trim(raw.startDate),
    description: truncate(raw.description, MAX_LENGTHS.description),
    artwork: truncate(raw.artwork, MAX_LENGTHS.artwork),
    contact: truncate(raw.contact, MAX_LENGTHS.contact),
    notes: truncate(raw.notes, MAX_LENGTHS.notes),
    authorizationConfirmed: raw.authorizationConfirmed === true,
    turnstileToken: truncate(raw.turnstileToken, 4096),
    honeypot: trim(raw.companyWebsite),
  };
  payload.podcastName = payload.title || payload.speaker || "Existing feed";
  return payload;
}

function decodeXmlEntities(value) {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(parseInt(code, 16)))
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function cleanFeedText(value) {
  return decodeXmlEntities(value || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, FEED_METADATA_MAX_LENGTH);
}

function blockFromXml(xml, tag) {
  return xml.match(new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, "i"))?.[1] || "";
}

function textFromXml(xml, tag) {
  return cleanFeedText(blockFromXml(xml, tag));
}

function attributeFromXml(xml, tag, attribute) {
  const escapedTag = tag.replace(":", "\\:");
  const escapedAttribute = attribute.replace(":", "\\:");
  const pattern = new RegExp(`<${escapedTag}\\b[^>]*\\s${escapedAttribute}=["']([^"']+)["'][^>]*>`, "i");
  return cleanFeedText(xml.match(pattern)?.[1] || "");
}

function resolveFeedUrl(feedUrl, value) {
  if (!value) {
    return "";
  }
  try {
    return new URL(value, feedUrl).toString();
  } catch {
    return value;
  }
}

function parseFeedMetadata(xml, feedUrl) {
  const root = blockFromXml(xml, "channel") || blockFromXml(xml, "feed") || xml;
  const title = textFromXml(root, "title");
  const author = textFromXml(root, "itunes:author") || textFromXml(root, "author") || textFromXml(root, "name");
  const link = resolveFeedUrl(feedUrl, textFromXml(root, "link") || attributeFromXml(root, "link", "href"));
  const artwork = resolveFeedUrl(
    feedUrl,
    attributeFromXml(root, "itunes:image", "href") || textFromXml(blockFromXml(root, "image"), "url"),
  );
  return { title, author, link, artwork };
}

async function enrichExistingFeedPayload(payload) {
  const { feed } = sourceUrls(payload);
  if (!feed || !sourceDefinition(payload.source)?.urlFields.includes("feed")) {
    return payload;
  }
  try {
    const result = await fetchFeedMetadata(feed);
    if (!result) return payload;
    const metadata = parseFeedMetadata(result.xml, result.url);
    payload.feedTitle = metadata.title;
    payload.feedAuthor = metadata.author;
    payload.feedWebsite = metadata.link;
    payload.feedArtwork = metadata.artwork;
    payload.podcastName = metadata.title || payload.podcastName;
  } catch {
    console.warn("onboarding_feed_metadata_unavailable");
  }
  return payload;
}

async function readResponseTextLimited(response) {
  if (!response.body) return "";
  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_FEED_BYTES) {
      await reader.cancel();
      throw new Error("feed_too_large");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}

function isXmlContentType(value) {
  return /(?:application\/(?:rss\+xml|atom\+xml|xml)|text\/xml)/i.test(value || "");
}

async function fetchFeedMetadata(initialUrl) {
  let current = safeHttpsUrl(initialUrl);
  if (!current) throw new Error("unsafe_feed_url");
  for (let redirects = 0; redirects <= MAX_FEED_REDIRECTS; redirects += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10_000);
    let response;
    try {
      response = await fetch(current.toString(), {
        redirect: "manual",
        signal: controller.signal,
        headers: {
          "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
          "User-Agent": "torah-pod-onboarding-worker",
        },
      });
    } finally {
      clearTimeout(timer);
    }
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const next = response.headers.get("Location");
      current = next ? safeHttpsUrl(new URL(next, current).toString()) : null;
      if (!current || redirects === MAX_FEED_REDIRECTS) throw new Error("unsafe_feed_redirect");
      continue;
    }
    if (!response.ok) return null;
    const xml = await readResponseTextLimited(response);
    if (!isXmlContentType(response.headers.get("Content-Type")) && !xml.trimStart().startsWith("<")) return null;
    return { url: current.toString(), xml };
  }
  return null;
}

function validatePayload(payload) {
  const errors = [];
  const definition = sourceDefinition(payload.source);
  if (!definition) {
    errors.push("Invalid source type.");
  }
  if (!definition?.urlFields.includes("feed") && !payload.speaker) {
    errors.push("Speaker / rabbi name is required.");
  }
  const hasFeed = definition?.urlFields.includes("feed");
  if (!hasFeed && (!payload.slug || !SLUG_RE.test(payload.slug))) {
    errors.push("Feed URL name is required and must use only lowercase English letters, numbers, and hyphens.");
  }
  const urls = sourceUrls(payload);
  if (definition?.urlFields.includes("youtube") && (!urls.youtube || !validateUrl(urls.youtube, "youtube"))) {
    errors.push("YouTube URL is invalid.");
  }
  if (definition?.urlFields.includes("drive") && (!urls.drive || !validateUrl(urls.drive, "drive"))) {
    errors.push("Google Drive folder URL is invalid.");
  }
  if (hasFeed && (!urls.feed || !validateUrl(urls.feed, "feed"))) {
    errors.push("Existing podcast feed URL is invalid.");
  }
  if (!hasFeed && !/^\d{4}-\d{2}-\d{2}$/.test(payload.startDate)) {
    errors.push("Start date must be YYYY-MM-DD.");
  }
  if (!validateEmail(payload.contact)) {
    errors.push("Contact email is invalid.");
  }
  if (payload.artwork && !validateUrl(payload.artwork, "any")) {
    errors.push("Artwork URL must be an https URL.");
  }
  if (!payload.authorizationConfirmed) {
    errors.push("You must confirm that you own the content or are authorized to submit it.");
  }
  if (!payload.turnstileToken) {
    errors.push("Verification is required.");
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
  const hasFeed = definition?.urlFields.includes("feed");
  const isPlaylist = hasYouTube && isYouTubePlaylistUrl(urls.youtube);
  const parts = [];
  if (hasYouTube) {
    parts.push(isPlaylist ? "YouTube playlist" : "YouTube channel");
  }
  if (hasDrive) {
    parts.push("Google Drive folder");
  }
  if (hasFeed) {
    parts.push("existing podcast feed");
  }
  return parts.join(" + ");
}

function issueTitle(payload) {
  if (sourceDefinition(payload.source)?.urlFields.includes("feed")) {
    return `Existing feed onboarding: ${payload.podcastName}`;
  }
  return `${sourceLabel(payload)} podcast onboarding: ${payload.podcastName}`;
}

function issueBody(payload) {
  const definition = sourceDefinition(payload.source);
  const { youtube: youtubeUrl, drive: driveUrl, feed: feedUrl } = sourceUrls(payload);
  const isPlaylist = isYouTubePlaylistUrl(youtubeUrl);
  const hasYouTube = definition?.urlFields.includes("youtube");
  const hasDrive = definition?.urlFields.includes("drive");
  const hasFeed = definition?.urlFields.includes("feed");
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
  if (hasFeed) {
    creatorLines.push("- Existing podcast feed is public and has audio enclosures: yes");
  }
  const reviewTargets = [
    ...(hasYouTube ? [`YouTube source at ${youtubeUrl}`] : []),
    ...(hasDrive ? [`Google Drive folder at ${driveUrl}`] : []),
    ...(hasFeed ? [`existing podcast feed at ${feedUrl}`] : []),
  ].join(", ");
  return [
    "## Podcast onboarding request",
    "",
    `- Source type: ${sourceLabel(payload)}`,
    ...(youtubeUrl ? [`- YouTube URL: ${youtubeUrl}`] : []),
    ...(driveUrl ? [`- Drive URL: ${driveUrl}`] : []),
    ...(feedUrl ? [`- Existing feed URL: ${feedUrl}`] : []),
    ...(!youtubeUrl && !driveUrl && !feedUrl ? [`- Source URL: ${payload.sourceUrl}`] : []),
    `- Podcast name: ${payload.title || "Not provided"}`,
    `- Feed slug: ${payload.slug || "Not provided"}`,
    `- Speaker / rabbi: ${payload.speaker || "Not provided"}`,
    `- Start date: ${payload.startDate || "Not provided"}`,
    `- Artwork URL: ${payload.artwork || "Not provided"}`,
    `- Contact email: ${payload.contact || "Not provided"}`,
    ...(hasFeed && (payload.feedTitle || payload.feedAuthor || payload.feedWebsite || payload.feedArtwork)
      ? [
          "",
          "## Discovered feed metadata",
          "",
          ...(payload.feedTitle ? [`- Title: ${payload.feedTitle}`] : []),
          ...(payload.feedAuthor ? [`- Author: ${payload.feedAuthor}`] : []),
          ...(payload.feedWebsite ? [`- Website: ${payload.feedWebsite}`] : []),
          ...(payload.feedArtwork ? [`- Artwork: ${payload.feedArtwork}`] : []),
        ]
      : []),
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
    "- Requester confirms authority to let Torah Pod host and distribute the content: yes",
    "- Torah Pod approval is required before a feed is created: yes",
    "",
    "## Maintainer approval",
    "",
    hasDrive
      ? `1. Review ${reviewTargets}, then run the Check Drive Folder workflow for ${driveUrl}.`
      : `1. Review ${reviewTargets}.`,
    "2. If approved, add the `approved` label.",
    "3. The approval workflow creates the show, syncs first episodes, deploys the feed, comments here, and closes this issue.",
  ].join("\n");
}

function githubHeaders(env, accept = "application/vnd.github+json", includeToken = true) {
  const headers = {
    "Accept": accept,
    "User-Agent": "torah-pod-onboarding-worker",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  if (includeToken && env.GITHUB_TOKEN) {
    headers.Authorization = `Bearer ${env.GITHUB_TOKEN}`;
  }
  return headers;
}

async function githubJson(env, url, includeToken = true) {
  const response = await fetch(url, { headers: githubHeaders(env, "application/vnd.github+json", includeToken) });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.message || `GitHub request failed: ${response.status}`);
    error.status = response.status;
    error.responseBody = body;
    throw error;
  }
  return body;
}

async function githubText(env, url, includeToken = true) {
  const response = await fetch(url, {
    headers: githubHeaders(env, "application/vnd.github.raw+json", includeToken),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    const error = new Error(body || `GitHub request failed: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.text();
}

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

async function findExistingShowDuplicate(env, repo, requestedKeys) {
  if (requestedKeys.size === 0) {
    return null;
  }
  const tree = await githubJson(
    env,
    `https://api.github.com/repos/${repo}/git/trees/main?recursive=1`,
    false,
  );
  const configPaths = (tree.tree || [])
    .map((item) => item.path || "")
    .filter((path) => /^shows\/[^/]+\/config\.ya?ml$/.test(path));

  for (const path of configPaths) {
    const slug = path.split("/")[1];
    const configText = await githubText(
      env,
      `https://api.github.com/repos/${repo}/contents/${encodePath(path)}?ref=main`,
      false,
    );
    for (const source of sourceBlocksFromConfigYaml(configText)) {
      for (const key of sourceSignatureKeysFromValues(source.type || "youtube", source)) {
        if (requestedKeys.has(key)) {
          return { slug };
        }
      }
    }
  }
  return null;
}

async function findOpenIssueDuplicate(env, repo, requestedKeys) {
  if (requestedKeys.size === 0) {
    return null;
  }
  const issues = await githubJson(
    env,
    `https://api.github.com/repos/${repo}/issues?state=open&labels=needs-approval&per_page=100`,
  );
  for (const issue of issues || []) {
    if (issue.pull_request) {
      continue;
    }
    for (const key of issueSourceSignatureKeys(issue)) {
      if (requestedKeys.has(key)) {
        return issue;
      }
    }
  }
  return null;
}

async function findDuplicateOnboardingSource(env, sourceRepo, intakeRepo, payload) {
  const requestedKeys = new Set(requestedSourceSignatureKeys(payload));
  try {
    const existingShow = await findExistingShowDuplicate(env, sourceRepo, requestedKeys);
    if (existingShow) {
      return {
        type: "show",
        slug: existingShow.slug,
        url: `https://torah-pod.pages.dev/${existingShow.slug}/`,
      };
    }
    const existingIssue = await findOpenIssueDuplicate(env, intakeRepo, requestedKeys);
    if (existingIssue) {
      return {
        type: "issue",
        number: existingIssue.number,
        url: existingIssue.html_url,
      };
    }
  } catch (error) {
    console.warn("Duplicate onboarding check failed", error.responseBody || error);
  }
  return null;
}

async function createGitHubIssue(env, payload, includeLabels = true) {
  const repo = env.INTAKE_REPO || "shaqo88/torah-pod-intake";
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
      ...githubHeaders(env),
      "Content-Type": "application/json",
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

async function allowSubmission(limiter, key) {
  if (!limiter || typeof limiter.limit !== "function") throw new Error("rate_limiter_unavailable");
  const result = await limiter.limit({ key });
  return result?.success === true;
}

function allowedTurnstileHostnames(env) {
  return String(env.TURNSTILE_ALLOWED_HOSTNAMES || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

async function verifyTurnstile(request, env, token) {
  if (!env.TURNSTILE_SECRET || !token) return false;
  const body = new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token });
  const remoteIp = request.headers.get("CF-Connecting-IP");
  if (remoteIp) body.set("remoteip", remoteIp);
  let response;
  try {
    response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch {
    return false;
  }
  const result = await response.json().catch(() => null);
  const hostname = String(result?.hostname || "").toLowerCase();
  return Boolean(
    response.ok &&
    result?.success === true &&
    result?.action === SUBMIT_ACTION &&
    allowedTurnstileHostnames(env).includes(hostname),
  );
}

function workerError(request, env, category) {
  console.warn(category, request.headers.get("CF-Ray") || "");
  return jsonResponse(request, env, 502, { ok: false, error: "Could not create GitHub issue." });
}

export async function handleSubmit(request, env) {
  const origin = requestOrigin(request, env);
  if (!origin) return jsonResponse(request, env, 403, { ok: false, error: "Verification failed." }, "");
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers.get("Content-Type") || "")) {
    return jsonResponse(request, env, 415, { ok: false, error: "Invalid request." }, origin);
  }
  let text;
  try {
    text = await request.text();
  } catch {
    return jsonResponse(request, env, 400, { ok: false, error: "Invalid JSON." }, origin);
  }
  if (new TextEncoder().encode(text).byteLength > MAX_REQUEST_BYTES) {
    return jsonResponse(request, env, 413, { ok: false, error: "Invalid request." }, origin);
  }
  let raw;
  try { raw = JSON.parse(text); } catch {
    return jsonResponse(request, env, 400, { ok: false, error: "Invalid JSON." }, origin);
  }

  const payload = normalizePayload(raw);
  if (payload.honeypot) {
    return jsonResponse(request, env, 200, { ok: true, ignored: true }, origin);
  }

  const errors = validatePayload(payload);
  if (errors.length > 0) {
    return jsonResponse(request, env, 400, { ok: false, errors }, origin);
  }

  try {
    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    const [globalAllowed, ipAllowed] = await Promise.all([
      allowSubmission(env.GLOBAL_SUBMIT_LIMITER, "onboarding-submit"),
      allowSubmission(env.PER_IP_SUBMIT_LIMITER, ip),
    ]);
    if (!globalAllowed || !ipAllowed) {
      return new Response(JSON.stringify({ ok: false, error: "Please try again in a minute." }), {
        status: 429,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
          "Retry-After": "60",
          ...corsHeaders(origin),
        },
      });
    }
  } catch {
    return workerError(request, env, "onboarding_rate_limiter_unavailable");
  }

  if (!(await verifyTurnstile(request, env, payload.turnstileToken))) {
    return jsonResponse(request, env, 403, { ok: false, error: "Verification failed." }, origin);
  }

  await enrichExistingFeedPayload(payload);

  if (!env.GITHUB_TOKEN) {
    return jsonResponse(request, env, 500, { ok: false, error: "Service unavailable." }, origin);
  }

  const sourceRepo = env.SOURCE_REPO || "shaqo88/youtube-podcast-feeds";
  const intakeRepo = env.INTAKE_REPO || "shaqo88/torah-pod-intake";
  const duplicate = await findDuplicateOnboardingSource(env, sourceRepo, intakeRepo, payload);
  if (duplicate?.type === "show") {
    return jsonResponse(request, env, 409, {
      ok: false,
      error: "This source is already listed in Torah Pod.",
    }, origin);
  }
  if (duplicate?.type === "issue") {
    return jsonResponse(request, env, 409, {
      ok: false,
      error: "There is already an open onboarding request for this source.",
    }, origin);
  }

  let issue;
  try {
    issue = await createGitHubIssue(env, payload, true);
  } catch (error) {
    if (error.status !== 422) {
      return workerError(request, env, "onboarding_github_issue_create_failed");
    }
    issue = await createGitHubIssue(env, payload, false);
  }

  return jsonResponse(request, env, 201, {
    ok: true,
  }, origin);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = requestOrigin(request, env);

    if (request.method === "OPTIONS") {
      if (url.pathname !== "/submit" || !origin) {
        return jsonResponse(request, env, 403, { ok: false, error: "Verification failed." }, "");
      }
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
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
