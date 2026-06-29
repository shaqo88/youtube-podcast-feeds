# Cloudflare Pages Deployment

The static Torah Pod site is already deployed by GitHub Pages.

Cloudflare Pages is prepared as an optional next hosting target:

```text
https://torah-pod.pages.dev
```

The workflow deploys automatically when files under `public/` change and can
also be run manually:

```text
Actions -> Deploy Cloudflare Pages -> Run workflow
```

## Required Cloudflare setup

The repository uses a Pages-specific GitHub Actions secret:

```text
CLOUDFLARE_PAGES_API_TOKEN
```

The token needs Pages edit/deploy permission for the account that owns the
project.

The workflow creates or reuses the `torah-pod` Pages project and deploys the
checked-in `public/` directory.

## Onboarding Worker CORS

`workers/onboarding/wrangler.toml` already allows both origins:

```text
https://shaqo88.github.io
https://torah-pod.pages.dev
```

After the Cloudflare token is updated, redeploy the onboarding Worker too:

```text
Actions -> Deploy Onboarding Worker -> Run workflow
```
