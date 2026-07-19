# Project Governance and Repository Boundaries

This document records the stable public boundary for Torah Pod. It is not legal
advice.

## Public Repository

`shaqo88/youtube-podcast-feeds` is public. It contains the application source,
public show configuration, generated site and feeds, minimal component usage
instructions, contribution rules, and the workflows needed to build and
publish the service.

Public issues are for developer feedback and reproducible product defects.
They must not contain podcast requests, contact details, credentials, private
Drive links, authorization records, or other private onboarding information.

## Private Operations Repository

`shaqo88/torah-pod-intake` is private and must remain private. It is the single
home for:

- onboarding requests, contact details, source links, authorization records,
  and private review discussion;
- active and future implementation plans;
- internal architecture and security details;
- infrastructure setup, operator runbooks, recovery procedures, and incident
  or migration history.

Internal documents are not duplicated into the public repository after a
feature is implemented. Public documentation describes only stable behavior
needed by listeners, requesters, contributors, or users of the checked-in
source.

## Request Lifecycle

1. A visitor submits the public onboarding form and confirms authorization.
2. The onboarding service creates a private review record and returns only a
   generic success response.
3. The repository owner reviews the private request.
4. Owner approval dispatches the public publishing workflow.
5. The public workflow validates the approved request and publishes only the
   configuration and assets intended to be public.

Private issue contents, reviewer notes, and authorization evidence must not be
copied into public commits, logs, artifacts, issues, or browser responses.

## Secrets and Access

Secret values are stored only in GitHub or platform secret stores. Access must
be repository-scoped, least-privilege, and separated by responsibility so that
private issue access does not automatically grant source-deployment access.
Exact token names, scopes, rotation steps, and recovery procedures are kept in
the private security and runbook documentation.

## Rights and Licensing

The root `LICENSE` applies to material first published on or after July 19,
2026. Earlier releases published under MIT remain available under their
original terms.

Torah Pod does not claim ownership of third-party recordings, artwork,
trademarks, or other supplied content. Each requester must confirm that they
own the content or are authorized to let Torah Pod host and distribute it.

## Visibility Policy

Keep the source repository public while public use and developer feedback are
valuable. Keep the operations repository private permanently because it stores
private requests and security-sensitive operating context. Review repository
access, automation permissions, and credential scopes before any visibility or
ownership change.
