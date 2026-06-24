# Onboarding Worker Setup

The public onboarding form can submit directly to a Cloudflare Worker. The
Worker creates a GitHub issue in this repo, so the creator does not need a
GitHub account or email client.

## 1. GitHub Token

Create a fine-grained GitHub personal access token:

- Repository access: `shaqo88/youtube-podcast-feeds` only
- Repository permissions:
  - `Issues`: Read and write
  - `Metadata`: Read-only

Store it as the GitHub Actions secret:

```text
ONBOARDING_GITHUB_TOKEN
```

## 2. Cloudflare Secrets

Create a Cloudflare API token that can deploy Workers for the account.

Store these GitHub Actions secrets:

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
```

`CLOUDFLARE_ACCOUNT_ID` can use the same value as the R2 account ID.

## 3. Deploy Worker

Run:

```text
Actions -> Deploy Onboarding Worker -> Run workflow
```

Copy the deployed Worker URL from the logs. It should look like:

```text
https://youtube-podcast-onboarding.<your-subdomain>.workers.dev
```

## 4. Connect The Public Page

Create or update the GitHub Actions repository variable:

```text
ONBOARDING_WORKER_ENDPOINT=https://youtube-podcast-onboarding.<your-subdomain>.workers.dev
```

Then run:

```text
Actions -> Deploy GitHub Pages -> Run workflow
```

After that, `https://shaqo88.github.io/youtube-podcast-feeds/onboard/` submits
directly to the Worker and creates a GitHub issue.

## Approval Flow

Each created issue keeps manual approval explicit:

- Source check passed
- Torah Pod approved this podcast
- Show config added
- First sync completed
