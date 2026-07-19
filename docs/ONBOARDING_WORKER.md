# Onboarding Worker Setup

The public onboarding form can submit directly to a Cloudflare Worker. The
Worker creates a private GitHub intake issue, so the creator does not need a
GitHub account or email client.

## 1. GitHub Token

Create a fine-grained GitHub personal access token:

- Repository access:
  - `shaqo88/torah-pod-intake`: Issues read/write
  - `shaqo88/youtube-podcast-feeds`: Contents read for duplicate detection

Store it as the GitHub Actions secret:

```text
ONBOARDING_INTAKE_TOKEN
```

Store the same token as `GITHUB_TOKEN` in the Cloudflare Worker. Also store it
as `ONBOARDING_INTAKE_TOKEN` in the public source repository so the approval
workflow can read and close the private intake issue.

## Private Intake Automation

The private `shaqo88/torah-pod-intake` repository needs the onboarding
notification and approval-dispatch workflows before private intake is enabled.
Its approval-dispatch workflow uses a separate fine-grained token stored as
`SOURCE_REPO_DISPATCH_TOKEN`. Limit that token to Actions write access for
`shaqo88/youtube-podcast-feeds`; it dispatches `approve_onboarding.yml` with
the private issue number. Copy `GMAIL_USER`, `GMAIL_APP_PASSWORD`, and optional
`PODCAST_NOTIFY_EMAIL` to the private repository for intake notifications.

Create these labels in the private repository:

```text
needs-approval
approved
youtube-onboarding
drive-onboarding
feed-onboarding
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

After that, `https://torah-pod.pages.dev/onboard/` submits
directly to the Worker and creates a private GitHub issue.

## Approval Flow

Each private intake issue keeps manual approval explicit:

- Source check passed
- Torah Pod approved this podcast
- Show config added
- First sync completed
