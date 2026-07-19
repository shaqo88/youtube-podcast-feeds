# Project Governance and Repository Boundaries

This document records the current operational and rights boundaries for Torah
Pod. It is not legal advice.

## Public Repository

`shaqo88/youtube-podcast-feeds` is public. It contains the Torah Pod
application code, site generator, feed configuration, generated public site,
and GitHub Actions workflows used to sync and publish feeds.

Developer feedback through public GitHub issues is welcome. Public onboarding
issue templates are intentionally disabled: podcast requests can include
contact details and other non-public information.

## Rights and Licensing

The root `LICENSE` applies to material first published on or after July 19,
2026: Torah Pod code, design, and brand are all rights reserved and cannot be
copied, modified, redistributed, hosted, or used commercially without written
permission. Earlier releases that were published under MIT remain available
under their original MIT license.

Torah Pod does not claim ownership of third-party recordings, artwork,
trademarks, or other supplied content. Their rights remain with the respective
rights holders. Each generated RSS feed uses neutral third-party rights
attribution rather than asserting that Torah Pod owns a show's media.

The public site states these terms at `/terms/` and asks submitters to confirm
that they own the content or are authorized to let Torah Pod host and distribute
it.

## Private Intake Repository

`shaqo88/torah-pod-intake` is private. It receives podcast onboarding requests
and holds the request metadata, including contact details, source links, and
the submitter's authorization confirmation. It must not be made public.

It has two workflows:

- `Notify Onboarding Request` emails new onboarding requests to the configured
  recipients.
- `Dispatch Approved Onboarding Request` runs when the repository owner adds
  the `approved` label. It invokes the public repository's approval workflow.

## Request Lifecycle

1. A visitor submits the public `/onboard/` form and confirms authorization.
2. The Cloudflare Worker creates a labeled issue in the private intake
   repository. The browser receives a generic success response; it does not
   receive a GitHub issue URL or number.
3. The private repository emails the configured recipients.
4. The repository owner reviews the private issue and adds the `approved`
   label.
5. The private dispatcher starts `Approve Onboarding Issue` in the public
   source repository, passing only the private issue number and intake
   repository name.
6. The public workflow reads the private request, validates authorization,
   creates the show configuration and public assets, then closes the private
   intake issue.

## Tokens and Secrets

Secret values are never stored in either repository. Current boundaries are:

| Secret | Stored in | Limited access | Purpose |
| --- | --- | --- | --- |
| `ONBOARDING_INTAKE_TOKEN` | public source repository | private intake repository, Issues read/write | Deployed Worker creates intake issues; public approval workflow reads/closes them. |
| `SOURCE_REPO_DISPATCH_TOKEN` | private intake repository | public source repository, Actions read/write | Dispatches the public approval workflow after an owner approves a request. |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `PODCAST_NOTIFY_EMAIL` | private intake repository | email delivery only | Sends private intake notifications. |

The public source repository separately has Gmail secrets for its existing
episode and workflow notifications. Rotate app passwords in both repositories
together.

## Visibility Policy

Keep the source repository public while developer feedback is valuable. Keep
the intake repository private permanently because it is a contact and approval
system. If the source repository becomes private later, review GitHub Actions,
Cloudflare deployment credentials, and all token repository scopes before
changing visibility.
