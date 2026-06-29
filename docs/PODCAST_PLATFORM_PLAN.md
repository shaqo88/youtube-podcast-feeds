# Torah Pod Podcast Platform Plan

## Summary

Build v1 in `youtube-podcast-feeds` as the platform monorepo, without renaming
or breaking existing feed URLs. Keep the current RSS/R2/GitHub Actions
ingestion system working, then add a website, API, auth, creator request flow,
and admin approval layer around it.

Default choices:

- V1: website only.
- V1 hosting: free static hosting, first through the existing GitHub Pages
  workflow and later through a free `pages.dev` Cloudflare Pages URL.
- Backend: Cloudflare Workers + D1 when the app needs account state, keeping R2
  for media.
- Auth: Clerk free tier for listener/creator/admin login, mapped to app roles
  in D1.
- RSS: remains first-class and public for approved podcasts.
- Mobile: later shared app codebase, not an AntennaPod fork.

## Phased Roadmap

### V0 - Current System

- Keep `youtube-podcast-feeds` as the active multi-podcast repository.
- Continue using GitHub Actions to sync YouTube/Drive sources, upload media to
  R2, build RSS feeds, validate output, and deploy `public/`.
- Keep existing public feed URLs stable for Apple Podcasts, Spotify, and other
  podcast apps.

### V1 - Free Static Listener Website

- Generate a public Torah Pod website from existing `shows/*/config.yml` and
  `shows/*/episodes.json`.
- Include homepage, podcast catalog, show pages, episode lists, artwork, RSS
  links, source links, browser audio playback, and basic client-side search.
- Use Hebrew as the primary UI language, with an English selector for core UI
  labels.
- Deploy with the current GitHub Pages workflow first. Move to Cloudflare Pages
  free `pages.dev` hosting later if desired.
- Do not require Clerk, D1, Workers, paid hosting, or a custom domain for this
  version.

### V2 - Cloudflare Pages Hosting

- Add Cloudflare Pages deployment for the same static `public/` output.
- Use the free `https://torah-pod.pages.dev` URL until a custom domain is
  worth buying.
- Keep GitHub Pages available during the transition so existing links do not
  break.
- Update the onboarding Worker allowed origins after the final Pages URL is
  known.

### V3 - Login And Listener Library

- Add Clerk authentication on the website.
- Keep public listening available without login.
- Add listener account features: subscriptions, favorites, playback progress,
  and listening history.
- Store account state in D1 through a Cloudflare Worker API.

### V4 - Creator And Admin Portal

- Replace or supplement the current public onboarding form with logged-in
  creator requests.
- Let creators submit podcasts and additional sources, then view request,
  approval, and sync status.
- Keep final approval with the Torah Pod admin account.
- Add admin screens for approve/reject, metadata edits, source visibility,
  hidden episodes, sync failures, and manual resync actions.

### V5 - Additional Connectors

- Add an `existing_feed` connector for importing another podcast RSS/Atom feed
  into a Torah Pod show.
- Keep YouTube channel, YouTube playlist, and Google Drive folder connectors.
- Design new connectors as source plugins so future sources can write to the
  same feed without changing the public RSS model.
- Avoid fuzzy duplicate merging in early versions; exact duplicate source
  identities are skipped and suspected duplicates are handled by admin review.

### V6 - Mobile Apps

- Build mobile apps after the website/API product is proven.
- Prefer one shared React Native/Expo app for Android and iOS.
- Use the same API, auth, catalog, listener library, and playback state as the
  website.
- Treat AntennaPod as product reference only unless there is a deliberate GPL
  compliance decision for an Android-only fork.

### V7 - Scale And Operations

- Move scheduled/background jobs from GitHub Actions to Cloudflare Cron/Queues
  only if GitHub Actions becomes limiting.
- Add richer monitoring for sync failures, source health, R2 storage usage, and
  feed validation.
- Consider a paid custom domain and custom R2 media domain only after the free
  URLs are stable and the project has enough usage to justify the annual cost.

## Key Changes

- Add an app database with these core tables: `shows`, `sources`, `episodes`,
  `sync_runs`, `users`, `creator_memberships`, `approval_requests`,
  `subscriptions`, `favorites`, and `playback_progress`.
- Keep YAML/JSON/RSS generation as the feed source of truth during v1. After
  each sync/build, GitHub Actions also upserts shows, sources, episodes, and
  sync status into D1 through a signed internal Worker endpoint.
- Add an `existing_feed` connector alongside YouTube and Drive:
  - Input: RSS/Atom feed URL.
  - Episode identity: source ID + upstream GUID, falling back to enclosure URL
    hash.
  - Default behavior: mirror audio to R2 when downloadable; store original
    enclosure URL and source page URL for traceability.
- Support many sources per podcast, but do not do fuzzy duplicate merging
  automatically in v1. Exact duplicate source IDs/enclosure URLs are skipped;
  suspected duplicates are shown to admin for manual unpublish/merge later.
- Add a public website with catalog, search, show page, episode page, HTML
  audio player, Hebrew/RTL support, and feed links.
- Add optional listener login for subscriptions, favorites, playback progress,
  and listening history.
- Add creator login for submitting podcast/source requests and viewing
  approval/sync status. You remain the only approver in v1.
- Add admin screens for approving/rejecting podcasts/sources, editing show
  metadata, hiding/unhiding episodes, and viewing sync failures.

## Interfaces

Public API:

- `GET /api/shows`
- `GET /api/shows/:slug`
- `GET /api/shows/:slug/episodes`
- `GET /api/search?q=...`

Authenticated listener API:

- `GET /api/me/library`
- `POST /api/me/subscriptions/:showId`
- `DELETE /api/me/subscriptions/:showId`
- `POST /api/me/episodes/:episodeId/progress`
- `POST /api/me/episodes/:episodeId/favorite`

Creator/admin API:

- `POST /api/creator/requests`
- `GET /api/creator/requests`
- `POST /api/admin/requests/:id/approve`
- `POST /api/admin/requests/:id/reject`
- `PATCH /api/admin/shows/:id`

Internal ingestion API:

- `POST /api/internal/sync-runs`
- `POST /api/internal/catalog-upsert`
- Protected by a shared secret stored in GitHub Actions and Cloudflare Worker
  secrets.

## Implementation Steps

- Stabilize current system first: add a `LICENSE` to `youtube-podcast-feeds`,
  document current repo as the v1 platform repo, and keep `enachmanson-feed`
  as migration-only.
- Create Cloudflare Worker API, D1 schema migrations, Clerk auth verification,
  and admin role bootstrapping by configured admin email.
- Add catalog export/upsert after existing sync/build workflows, preserving
  current RSS feed generation and validation.
- Build the website as a Cloudflare Pages app with anonymous browsing first,
  then add signed-in listener library and creator/admin dashboards.
- Add `existing_feed` connector with fixture-based tests, then expose it in
  creator requests and admin approval.
- After v1 website is stable, plan mobile as a shared React Native/Expo app
  consuming the same API. AntennaPod can be used for product reference only;
  its README says it is Android-only and GPL-3.0, and GPL distribution
  obligations would apply to a modified fork.

## Test Plan

- Unit tests for source parsing, RSS import, episode identity, duplicate
  prevention, and catalog upsert payloads.
- Existing feed validation continues for every generated RSS feed, including
  artwork, GUIDs, enclosure URLs, content type, and byte-range support.
- Worker API tests for anonymous, listener, creator, admin, and
  internal-ingestion authorization.
- Playwright tests for desktop/mobile website flows: browse, search, play, sign
  in, subscribe, resume progress, submit creator request, approve as admin.
- Migration acceptance: existing Nachmanson, Wechter, and Drive feeds keep
  their public feed URLs and episode GUIDs unchanged.

## Assumptions

- Public Torah podcasts stay publicly playable and available through normal RSS
  directories.
- Creator login in v1 is for requests/status, not full self-service publishing.
- Cloudflare D1 is appropriate for the app database because it is a managed
  serverless SQL database usable from Workers/Pages.
- Clerk is acceptable for auth because it supports web, Expo/React Native,
  native Android, and iOS SDKs.
- AntennaPod fork is not part of v1.

## References

- AntennaPod README:
  <https://raw.githubusercontent.com/AntennaPod/AntennaPod/develop/README.md>
- GPL-3.0:
  <https://www.gnu.org/licenses/gpl-3.0.en.html>
- Cloudflare D1 docs:
  <https://developers.cloudflare.com/d1/>
- Clerk docs:
  <https://clerk.com/docs>
